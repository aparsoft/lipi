"""Tests for the parallel batch processor."""

import json
from pathlib import Path

from lipi.batch import (
    BatchConfig,
    discover_files,
    process_path,
    run_batch,
    summarise,
    write_jsonl,
    _init_worker,
)


def _write_text_files(root: Path, samples: dict) -> list[Path]:
    paths = []
    for name, content in samples.items():
        path = root / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def test_discover_files_filters_by_extension(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "b.md").write_text("y", encoding="utf-8")
    found = discover_files(tmp_path, (".txt",))
    assert [p.name for p in found] == ["a.txt"]


def test_run_batch_single_worker_inline(tmp_path):
    paths = _write_text_files(
        tmp_path,
        {
            "f1.txt": "जन््मम की कथा",
            "f2.txt": "स््थथित प्रश्न",
        },
    )
    config = BatchConfig(workers=1, correction_mode="none")
    results = list(run_batch(paths, config))
    assert len(results) == 2
    by_path = {r["input_path"]: r for r in results}
    assert "जन्म" in by_path[str(paths[0])]["cleaned_text"]
    assert "स्थित" in by_path[str(paths[1])]["cleaned_text"]


def test_run_batch_multiprocess(tmp_path):
    paths = _write_text_files(
        tmp_path,
        {f"f{i}.txt": f"जन््मम पाठ {i}" for i in range(6)},
    )
    config = BatchConfig(workers=2, correction_mode="none")
    results = list(run_batch(paths, config))
    assert len(results) == 6
    for row in results:
        assert "जन्म" in row["cleaned_text"]


def test_write_jsonl_and_summarise(tmp_path):
    paths = _write_text_files(
        tmp_path,
        {
            "a.txt": "जन््मम के बारे में",
            "b.txt": "स््थथित कथा है",
        },
    )
    config = BatchConfig(workers=1, correction_mode="none")
    output = tmp_path / "out.jsonl"
    written = write_jsonl(run_batch(paths, config), output)
    assert written == 2
    summary = summarise(output)
    assert summary["files"] == 2
    assert summary["errors"] == 0
    assert summary["artifacts_removed"] > 0


def test_process_path_handles_missing_file(tmp_path):
    _init_worker(BatchConfig(workers=1).to_dict())
    result = process_path(str(tmp_path / "does_not_exist.txt"))
    assert "error" in result
