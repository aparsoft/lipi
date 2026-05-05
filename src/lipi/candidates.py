"""
Candidate-generator architecture for token-level corrections.

The legacy ``HindiPreprocessor.post_process`` pipeline applies regex rewrites
destructively: each rule mutates the text in place and the next rule sees the
mutated form. This works for clearly-broken legacy-font output but causes
silent damage on already-Devanagari text — the classic example is
``CC -> Cि`` rewriting ``रुककर -> रुकिर``.

This module reframes per-token rules as **candidate generators**. For every
token a rule may emit one or more candidate transforms (each carrying a
``confidence`` and a short ``reason``). A scorer (``select_best``) then picks
the winning candidate, optionally consulting an external lexicon and/or
language model. The original token is always a candidate, so a rule that fires
spuriously can be vetoed.

Public API:

* ``Candidate`` — dataclass describing one transform option.
* ``TokenRule`` — protocol for callables ``str -> List[Candidate]``.
* ``DEFAULT_TOKEN_RULES`` — built-in deterministic rules used by
  ``correct_text``.
* ``select_best`` — scorer that picks a winner among candidates.
* ``correct_text`` — apply rules + scorer to every Devanagari token in a
  string. Returns ``(corrected_text, stats)``.

Designed to be **opt-in**. The existing ``post_process`` API and behaviour are
unchanged; this module is wired in only via the new SymSpell pipeline and the
``lipi correct-corpus`` CLI command.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_WORD_RE = re.compile(r"[\u0900-\u0963\u0970-\u097f]+")
# Devanagari consonants: 0915-0939 (क-ह) + 0958-095F (precomposed nukta forms क़-य़)
_CONS_CLASS = "\u0915-\u0939\u0958-\u095f"
_DEVA_MARKS = "\u093c\u0901\u0902\u0903\u093e\u093f\u0940\u0941\u0942\u0943\u0947\u0948\u0949\u094b\u094c\u094d"

_DUPLICATE_HALANT_RE = re.compile(r"्{2,}")
_HALANT_DUPLICATE_CONSONANT_RE = re.compile(rf"्([{_CONS_CLASS}])\1")
_REPEATED_BASE_CONSONANT_RE = re.compile(rf"([{_CONS_CLASS}])\1")
_DUPLICATE_MARKS_RE = re.compile(r"([ँंः़ािीुूृेैोौ्])\1+")
_DUPLICATE_MARK_CLUSTER_RE = re.compile(r"([ािीुूृेैोौ][ँं])\1+")
_LEADING_YI_RE = re.compile(r"^यि")
_PRE_CLUSTER_IMATRA_RE = re.compile(rf"ि(?=[{_CONS_CLASS}]्)")
_PRE_ANUSVARA_CLUSTER_IMATRA_RE = re.compile(rf"ि(?=[ँं][{_CONS_CLASS}])")


@dataclass(frozen=True)
class Candidate:
    """One possible transform of a token."""

    text: str
    confidence: float
    reason: str

    def with_text(self, new_text: str) -> "Candidate":
        return Candidate(text=new_text, confidence=self.confidence, reason=self.reason)


TokenRule = Callable[[str], List[Candidate]]


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------


def keep_original(token: str) -> List[Candidate]:
    """Always emit the unchanged token as a low-confidence baseline."""
    return [Candidate(text=token, confidence=0.5, reason="keep")]


def collapse_duplicate_halant(token: str) -> List[Candidate]:
    """``जन््मम`` -> ``जन्मम`` (does not yet collapse the repeated base)."""
    if not _DUPLICATE_HALANT_RE.search(token):
        return []
    return [
        Candidate(
            text=_DUPLICATE_HALANT_RE.sub("्", token),
            confidence=0.9,
            reason="dup_halant",
        )
    ]


def collapse_halant_duplicate_consonant(token: str) -> List[Candidate]:
    """``्CC`` -> ``्C`` (e.g. ``स््थथित`` -> ``स्थित``)."""
    if not _HALANT_DUPLICATE_CONSONANT_RE.search(token):
        return []
    return [
        Candidate(
            text=_HALANT_DUPLICATE_CONSONANT_RE.sub(r"्\1", token),
            confidence=0.85,
            reason="halant_dup_cons",
        )
    ]


def collapse_repeated_base_consonant(token: str) -> List[Candidate]:
    """
    ``CC`` -> ``C``. Emitted as a *candidate*, not applied destructively.

    On legacy-font extractions this often recovers the lost ``ि``-matra; on
    clean Devanagari it would damage real geminates (``रुककर``, ``हमला``) —
    so we let the scorer decide.
    """
    if not _REPEATED_BASE_CONSONANT_RE.search(token):
        return []
    candidate_text = _REPEATED_BASE_CONSONANT_RE.sub(r"\1", token)
    if candidate_text == token:
        return []
    return [
        Candidate(
            text=candidate_text,
            confidence=0.55,  # below `keep_original` so lexicon must vote in
            reason="dup_consonant_collapse",
        )
    ]


def insert_imatra_for_doubled_consonant(token: str) -> List[Candidate]:
    """Legacy-font hypothesis: ``CC`` originally hid a lost ``ि``-matra."""
    if not _REPEATED_BASE_CONSONANT_RE.search(token):
        return []
    candidate_text = _REPEATED_BASE_CONSONANT_RE.sub(r"\1ि", token)
    if candidate_text == token:
        return []
    return [
        Candidate(
            text=candidate_text,
            confidence=0.45,
            reason="dup_consonant_imatra",
        )
    ]


def collapse_duplicate_marks(token: str) -> List[Candidate]:
    """``ाा`` / ``ँंँं`` -> single mark cluster."""
    if not (_DUPLICATE_MARKS_RE.search(token) or _DUPLICATE_MARK_CLUSTER_RE.search(token)):
        return []
    candidate_text = _DUPLICATE_MARKS_RE.sub(r"\1", token)
    candidate_text = _DUPLICATE_MARK_CLUSTER_RE.sub(r"\1", candidate_text)
    if candidate_text == token:
        return []
    return [
        Candidate(
            text=candidate_text,
            confidence=0.85,
            reason="dup_marks",
        )
    ]


def drop_stray_imatra(token: str) -> List[Candidate]:
    """
    Drop a stray ``ि`` for the well-known corruption signatures.

    Same gate as ``HindiLexiconCorrector._repair_stray_imatra_insertion``.
    """
    if "ि" not in token:
        return []
    if not (
        _LEADING_YI_RE.search(token)
        or _PRE_CLUSTER_IMATRA_RE.search(token)
        or _PRE_ANUSVARA_CLUSTER_IMATRA_RE.search(token)
    ):
        return []
    candidates: List[Candidate] = []
    seen: Set[str] = set()
    for index, char in enumerate(token):
        if char != "ि" or index >= len(token) - 1:
            continue
        new_text = token[:index] + token[index + 1 :]
        if new_text in seen:
            continue
        seen.add(new_text)
        candidates.append(Candidate(text=new_text, confidence=0.6, reason="drop_stray_imatra"))
    return candidates


DEFAULT_TOKEN_RULES: Tuple[TokenRule, ...] = (
    keep_original,
    collapse_duplicate_halant,
    collapse_halant_duplicate_consonant,
    collapse_duplicate_marks,
    collapse_repeated_base_consonant,
    insert_imatra_for_doubled_consonant,
    drop_stray_imatra,
)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass
class ScoringContext:
    """External knowledge sources consulted by ``select_best``."""

    lexicon: Optional[Set[str]] = None
    frequency: Optional[Dict[str, float]] = None
    lm_score: Optional[Callable[[str], float]] = None
    lexicon_bonus: float = 0.5
    frequency_weight: float = 0.05


def _candidate_score(candidate: Candidate, context: ScoringContext) -> float:
    score = candidate.confidence
    if context.lexicon is not None and candidate.text in context.lexicon:
        score += context.lexicon_bonus
    if context.frequency is not None:
        freq = context.frequency.get(candidate.text)
        if freq is not None and freq > 0:
            # log1p keeps the bonus bounded for very high-freq tokens.
            from math import log1p

            score += context.frequency_weight * log1p(freq)
    if context.lm_score is not None:
        try:
            score += context.lm_score(candidate.text)
        except Exception:
            pass
    return score


def select_best(
    candidates: Sequence[Candidate],
    context: Optional[ScoringContext] = None,
) -> Candidate:
    """Pick the highest-scoring candidate. Ties resolved by rule order."""
    if not candidates:
        raise ValueError("select_best requires at least one candidate")
    ctx = context or ScoringContext()
    best_index = 0
    best_score = _candidate_score(candidates[0], ctx)
    for index in range(1, len(candidates)):
        score = _candidate_score(candidates[index], ctx)
        if score > best_score:
            best_score = score
            best_index = index
    return candidates[best_index]


# ---------------------------------------------------------------------------
# Token pipeline
# ---------------------------------------------------------------------------


@dataclass
class TokenCorrection:
    original: str
    corrected: str
    reason: str


def generate_token_candidates(
    token: str,
    rules: Sequence[TokenRule] = DEFAULT_TOKEN_RULES,
    max_iterations: int = 4,
) -> List[Candidate]:
    """Run all rules against *token* and return de-duplicated candidates.

    Rules are also applied to previously-generated candidates so chained
    transforms (e.g. ``जन््मम → जन्मम → जन्म``) become reachable. The
    confidence of a chained candidate is the product of the contributing rule
    confidences, so every additional step is a hypothesis the scorer may
    veto.
    """
    seen: Dict[str, Candidate] = {token: Candidate(text=token, confidence=0.5, reason="keep")}
    frontier: List[Candidate] = [seen[token]]
    for _ in range(max_iterations):
        next_frontier: List[Candidate] = []
        for parent in frontier:
            for rule in rules:
                if rule is keep_original:
                    continue
                for candidate in rule(parent.text):
                    if candidate.text == parent.text:
                        continue
                    chained_confidence = parent.confidence * candidate.confidence if parent.reason != "keep" else candidate.confidence
                    chained_reason = candidate.reason if parent.reason == "keep" else f"{parent.reason}+{candidate.reason}"
                    chained = Candidate(
                        text=candidate.text,
                        confidence=chained_confidence,
                        reason=chained_reason,
                    )
                    existing = seen.get(chained.text)
                    if existing is None or chained.confidence > existing.confidence:
                        seen[chained.text] = chained
                        next_frontier.append(chained)
        if not next_frontier:
            break
        frontier = next_frontier
    return list(seen.values())


@dataclass
class CorrectionStats:
    tokens_seen: int = 0
    tokens_changed: int = 0
    corrections: List[TokenCorrection] = field(default_factory=list)
    rule_counts: Dict[str, int] = field(default_factory=dict)


def correct_text(
    text: str,
    rules: Sequence[TokenRule] = DEFAULT_TOKEN_RULES,
    context: Optional[ScoringContext] = None,
    max_recorded_corrections: int = 50,
) -> Tuple[str, CorrectionStats]:
    """Run candidate-based correction over every Devanagari token in *text*."""
    if not text:
        return text, CorrectionStats()

    stats = CorrectionStats()

    def replace(match: re.Match) -> str:
        token = match.group(0)
        stats.tokens_seen += 1
        candidates = generate_token_candidates(token, rules)
        winner = select_best(candidates, context)
        if winner.text == token:
            return token
        stats.tokens_changed += 1
        stats.rule_counts[winner.reason] = stats.rule_counts.get(winner.reason, 0) + 1
        if len(stats.corrections) < max_recorded_corrections:
            stats.corrections.append(
                TokenCorrection(original=token, corrected=winner.text, reason=winner.reason)
            )
        return winner.text

    return _WORD_RE.sub(replace, text), stats


def build_lexicon_context(
    lexicon: Iterable[str],
    frequency: Optional[Dict[str, float]] = None,
    lm_score: Optional[Callable[[str], float]] = None,
) -> ScoringContext:
    """Convenience: build a ``ScoringContext`` from common inputs."""
    return ScoringContext(
        lexicon=set(lexicon),
        frequency=frequency,
        lm_score=lm_score,
    )
