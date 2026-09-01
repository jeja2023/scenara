from __future__ import annotations

from pathlib import Path

from scripts.code_size_gate import MAX_CODE_LINES, violations


def test_repository_code_files_fit_within_the_size_budget() -> None:
    assert violations() == []


def test_code_size_gate_reports_an_over_budget_source_file(tmp_path: Path) -> None:
    source = tmp_path / "oversized.py"
    source.write_text("pass\n" * (MAX_CODE_LINES + 1), encoding="utf-8")

    assert violations(tmp_path) == [
        f"code size limit ({MAX_CODE_LINES} lines) exceeded: oversized.py ({MAX_CODE_LINES + 1} lines)"
    ]
