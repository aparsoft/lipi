"""Tests for the `lipi correct-corpus` CLI subcommand."""

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "lipi.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_correct_corpus_end_to_end(tmp_path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "a.txt").write_text("जन््मम की कथा", encoding="utf-8")
    (input_dir / "b.txt").write_text("स््थथित प्रश्न हैहै।", encoding="utf-8")

    output_jsonl = tmp_path / "out.jsonl"
    result = _run_cli(
        [
            "correct-corpus",
            str(input_dir),
            "-o",
            str(output_jsonl),
            "--correction-mode",
            "none",
            "--workers",
            "1",
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["files"] == 2
    assert summary["errors"] == 0
    assert summary["artifacts_removed"] > 0

    rows = [json.loads(line) for line in output_jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    cleaned_texts = "\n".join(row["cleaned_text"] for row in rows)
    assert "जन्म" in cleaned_texts
    assert "स्थित" in cleaned_texts
    assert "हैहै" not in cleaned_texts


def test_correct_corpus_missing_input_exits_nonzero(tmp_path):
    result = _run_cli(["correct-corpus", str(tmp_path / "missing"), "-o", str(tmp_path / "x.jsonl")])
    assert result.returncode != 0
    assert "not found" in result.stderr.lower()
