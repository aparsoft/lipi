"""Optional lexicon-based second-stage correction for extracted Hindi text."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Set

from lipi._lexicon import DEFAULT_HINDI_LEXICON

_WORD_RE = re.compile(r"[\u0900-\u0963\u0970-\u097f]+")
_DUPLICATE_MARKS_RE = re.compile(r"([ँंः़ािीुूृेैोौ्])\1+")
_SPURIOUS_NUKTA_RE = re.compile(r"[क-ह](?:्)?़")
_NONSTANDARD_NUKTA_RE = re.compile(r"[ञचछझटठतथदधनपबभमयरलवशषसहव](?:्)?़")
_SUSPICIOUS_MARK_SEQUENCE_RE = re.compile(r"[ािीुूृेैोौॉॅ][ँंः]?[ािीुूृेैोौॉॅ]")
_BROKEN_EMATRA_TOKEN_RE = re.compile(r"[ेै][ािीुूृोौ]")
_LEADING_IMATRA_TOKEN_RE = re.compile(r"^ि(?=[\u0900-\u097f])")
_J_IMATRA_SWAP_RE = re.compile(r"ज((?:[क-ह]्)*[क-ह])")
_ZERO_WIDTH_RE = re.compile(r"[\u200c\u200d]")
_DUPLICATE_HALANT_RE = re.compile(r"्{2,}")
_HALANT_DUPLICATE_CONSONANT_RE = re.compile(r"्([क-हक़-य़])\1")
# Full repeated-base consonant collapse is safe here because it is only used
# for exact normalized lexicon hits; tokens with no exact candidate are not
# allowed to fall through into fuzzy correction.
_REPEATED_BASE_CONSONANT_RE = re.compile(r"([क-हक़-य़])\1")
_DUPLICATE_MARK_CLUSTER_RE = re.compile(r"([ािीुूृेैोौ][ँं])\1+")
_LOOKUP_SEQUENCE_REPLACEMENTS = (
    ("ांे", "ों"),
    ("ाे", "ो"),
    ("ाै", "ौ"),
    ("ाॉ", "ॉ"),
    ("ेा", "ा"),
    ("ेो", "ो"),
)


def _normalize_lookup_token(word: str) -> str:
    """Normalize noisy tokens before lexicon lookup."""
    word = _ZERO_WIDTH_RE.sub("", word)
    previous = None
    for _ in range(4):
        previous = word
        word = _DUPLICATE_HALANT_RE.sub("्", word)
        word = _HALANT_DUPLICATE_CONSONANT_RE.sub(r"्\1", word)
        word = _REPEATED_BASE_CONSONANT_RE.sub(r"\1", word)
        word = _DUPLICATE_MARKS_RE.sub(r"\1", word)
        word = _DUPLICATE_MARK_CLUSTER_RE.sub(r"\1", word)
        for pattern, replacement in _LOOKUP_SEQUENCE_REPLACEMENTS:
            word = word.replace(pattern, replacement)
        if word == previous:
            break
    return word.replace("़", "").replace("्", "")


def _allowed_distance(token_length: int, max_distance: int) -> int:
    if token_length <= 4:
        return min(max_distance, 1)
    if token_length <= 7:
        return min(max_distance, 2)
    return min(max_distance, 3)


def _levenshtein_distance(source: str, target: str, max_distance: int) -> Optional[int]:
    """Bounded Levenshtein distance with early stopping."""
    if abs(len(source) - len(target)) > max_distance:
        return None

    previous_row = list(range(len(target) + 1))
    for source_index, source_char in enumerate(source, start=1):
        current_row = [source_index]
        row_min = current_row[0]
        for target_index, target_char in enumerate(target, start=1):
            insert_cost = current_row[target_index - 1] + 1
            delete_cost = previous_row[target_index] + 1
            replace_cost = previous_row[target_index - 1] + (source_char != target_char)
            value = min(insert_cost, delete_cost, replace_cost)
            current_row.append(value)
            row_min = min(row_min, value)

        if row_min > max_distance:
            return None
        previous_row = current_row

    distance = previous_row[-1]
    return distance if distance <= max_distance else None


def load_lexicon_words(lexicon_path: Optional[str] = None) -> Set[str]:
    """Load bundled lexicon plus optional user-supplied words."""
    words = set(DEFAULT_HINDI_LEXICON)
    if not lexicon_path:
        return words

    with open(lexicon_path, "r", encoding="utf-8") as handle:
        for token in _WORD_RE.findall(handle.read()):
            words.add(token)
    return words


def build_contextual_lexicon(
    texts: Iterable[str],
    base_lexicon: Optional[Set[str]] = None,
    min_frequency: int = 2,
    min_token_length: int = 4,
) -> Set[str]:
    """Build a supplemental lexicon from clean repeated tokens in the document set."""
    counter: Counter[str] = Counter()
    base_words = base_lexicon or set()

    for text in texts:
        for token in _WORD_RE.findall(text):
            if len(token) < min_token_length:
                continue
            if token in base_words:
                continue
            if _SPURIOUS_NUKTA_RE.search(token):
                continue
            if _DUPLICATE_MARKS_RE.search(token):
                continue
            counter[token] += 1

    return {token for token, freq in counter.items() if freq >= min_frequency}


class HindiLexiconCorrector:
    """Lexicon-guided token corrector for optional second-stage cleanup."""

    def __init__(
        self,
        lexicon_words: Optional[Iterable[str]] = None,
        lexicon_path: Optional[str] = None,
        max_distance: int = 2,
    ) -> None:
        self.max_distance = max_distance
        self.lexicon: Set[str] = set(lexicon_words or load_lexicon_words(lexicon_path))
        self._normalized_index: Dict[str, Set[str]] = defaultdict(set)
        self._normalized_cache: Dict[str, str] = {}
        self._words_by_length: Dict[int, Set[str]] = defaultdict(set)
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._normalized_index.clear()
        self._normalized_cache.clear()
        self._words_by_length.clear()
        for word in self.lexicon:
            normalized = _normalize_lookup_token(word)
            self._normalized_index[normalized].add(word)
            self._normalized_cache[word] = normalized
            self._words_by_length[len(normalized)].add(word)

    def add_words(self, words: Iterable[str]) -> None:
        new_words = set(words)
        if not new_words:
            return
        self.lexicon.update(new_words)
        self._rebuild_index()

    def _repair_direct_j_imatra_swap(self, token: str) -> Optional[str]:
        """Repair a common scrambled-Devanagari ज/ि swap when the candidate is exact."""
        if not (_LEADING_IMATRA_TOKEN_RE.search(token) or _J_IMATRA_SWAP_RE.search(token)):
            return None

        candidate = _LEADING_IMATRA_TOKEN_RE.sub("ज", token)
        candidate = _J_IMATRA_SWAP_RE.sub(lambda match: match.group(1) + "ि", candidate)
        if candidate != token and candidate in self.lexicon:
            return candidate
        return None

    def _repair_structural_duplication(self, token: str) -> Optional[str]:
        """Repair repeated-halant / repeated-consonant noise when an exact candidate exists."""
        if not (
            _DUPLICATE_HALANT_RE.search(token)
            or _HALANT_DUPLICATE_CONSONANT_RE.search(token)
            or _REPEATED_BASE_CONSONANT_RE.search(token)
            or _DUPLICATE_MARK_CLUSTER_RE.search(token)
        ):
            return None

        candidate = _normalize_lookup_token(token)
        if candidate != token and candidate in self.lexicon:
            return candidate
        return None

    def _suggest(self, token: str) -> Optional[str]:
        if token in self.lexicon:
            return token

        direct_swap_candidate = self._repair_direct_j_imatra_swap(token)
        if direct_swap_candidate:
            return direct_swap_candidate

        direct_structural_candidate = self._repair_structural_duplication(token)
        if direct_structural_candidate:
            return direct_structural_candidate

        normalized = _normalize_lookup_token(token)
        if not normalized:
            return None

        direct_matches = self._normalized_index.get(normalized)
        if direct_matches and len(direct_matches) == 1:
            return next(iter(direct_matches))
        if (
            _LEADING_IMATRA_TOKEN_RE.search(token)
            or _J_IMATRA_SWAP_RE.search(token)
            or _BROKEN_EMATRA_TOKEN_RE.search(token)
            or _DUPLICATE_HALANT_RE.search(token)
            or _HALANT_DUPLICATE_CONSONANT_RE.search(token)
            or _REPEATED_BASE_CONSONANT_RE.search(token)
            or _DUPLICATE_MARK_CLUSTER_RE.search(token)
        ):
            return None

        allowed_distance = _allowed_distance(len(normalized), self.max_distance)
        best_candidate: Optional[str] = None
        best_score: Optional[tuple[int, int, int]] = None
        tie_count = 0

        for candidate_length in range(
            max(1, len(normalized) - allowed_distance),
            len(normalized) + allowed_distance + 1,
        ):
            for candidate in self._words_by_length.get(candidate_length, set()):
                candidate_normalized = self._normalized_cache[candidate]
                if normalized[0] != candidate_normalized[0]:
                    continue

                distance = _levenshtein_distance(normalized, candidate_normalized, allowed_distance)
                if distance is None:
                    continue

                if _NONSTANDARD_NUKTA_RE.search(token) and token[-1] != candidate[-1]:
                    continue

                if distance > 1:
                    shares_prefix = normalized[:2] == candidate_normalized[:2]
                    shares_suffix = normalized[-3:] == candidate_normalized[-3:]
                    if not (shares_prefix or shares_suffix):
                        continue

                prefix_penalty = 0 if token[:2] == candidate[:2] else 1
                suffix_penalty = 0 if token[-1] == candidate[-1] else 1
                score = (
                    distance,
                    prefix_penalty + suffix_penalty,
                    abs(len(candidate) - len(token)),
                )

                if best_score is None or score < best_score:
                    best_candidate = candidate
                    best_score = score
                    tie_count = 1
                elif score == best_score:
                    tie_count += 1

        if tie_count != 1:
            return None
        return best_candidate

    def _should_consider(self, token: str, min_token_length: int) -> bool:
        if len(token) < min_token_length or token in self.lexicon:
            return False
        return bool(
            _LEADING_IMATRA_TOKEN_RE.search(token)
            or _J_IMATRA_SWAP_RE.search(token)
            or _DUPLICATE_HALANT_RE.search(token)
            or _HALANT_DUPLICATE_CONSONANT_RE.search(token)
            or _REPEATED_BASE_CONSONANT_RE.search(token)
            or _DUPLICATE_MARK_CLUSTER_RE.search(token)
            or _NONSTANDARD_NUKTA_RE.search(token)
            or _DUPLICATE_MARKS_RE.search(token)
            or _SUSPICIOUS_MARK_SEQUENCE_RE.search(token)
        )

    def correct_text(
        self,
        text: str,
        min_token_length: int = 4,
    ) -> Dict[str, object]:
        """Correct suspicious tokens with lexicon-guided replacements."""
        if not text:
            return {
                "text": text,
                "stats": {
                    "tokens_seen": 0,
                    "tokens_considered": 0,
                    "corrected_tokens": 0,
                    "corrections": [],
                    "lexicon_size": len(self.lexicon),
                },
            }

        corrections: List[Dict[str, str]] = []
        stats = {
            "tokens_seen": 0,
            "tokens_considered": 0,
            "corrected_tokens": 0,
            "corrections": corrections,
            "lexicon_size": len(self.lexicon),
        }

        def replace_token(match: re.Match) -> str:
            token = match.group(0)
            stats["tokens_seen"] += 1
            if not self._should_consider(token, min_token_length):
                return token

            stats["tokens_considered"] += 1
            candidate = self._suggest(token)
            if not candidate or candidate == token:
                return token

            stats["corrected_tokens"] += 1
            if len(corrections) < 20:
                corrections.append({"from": token, "to": candidate})
            return candidate

        corrected_text = _WORD_RE.sub(replace_token, text)
        return {"text": corrected_text, "stats": stats}
