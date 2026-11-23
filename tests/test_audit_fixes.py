"""Regression tests for the repo-audit fixes: bucket caps, eviction safety, host guard, upload limit, xlsx text cells."""

from __future__ import annotations

import csv
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from entity_standardizer.dedup import iter_bucket_pairs
from entity_standardizer.server import create_app
from entity_standardizer.workbench import io_formats
from entity_standardizer.workbench import match_runner as mr
from entity_standardizer.workbench.io_formats import FileFormatSpec, write_tabular_output, write_xlsx_sheets
from entity_standardizer.workbench.mapping import auto_detect_mappings
from entity_standardizer.workbench.router import WorkbenchWorkspace

REPO = Path(__file__).resolve().parent.parent
COLS = ["Company", "Street", "City", "State", "Zip"]


def _csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows([COLS, *rows])
    return path


def _mapping(rows: list[list[str]]):
    return auto_detect_mappings(COLS, [dict(zip(COLS, r)) for r in rows])


def test_iter_bucket_pairs_yields_each_pair_once() -> None:
    assert list(iter_bucket_pairs([[0, 1, 2], [2, 1], [3]])) == [(0, 1), (0, 2), (1, 2)]


def test_oversized_buckets_are_skipped_and_counted(tmp_path: Path, monkeypatch) -> None:
    rows = [["Edward Jones", f"{i} Main St", f"Town{i}", "TX", f"7000{i}"] for i in range(4)]
    src = _csv(tmp_path / "f.csv", rows)
    mapping = _mapping(rows)

    assert mr.run_single_file_dedup(src, mapping, mr.MatchingOptions()).summary["skipped_oversized_buckets"] == 0

    monkeypatch.setattr(mr, "_MAX_BUCKET_SIZE", 2)
    dedup = mr.run_single_file_dedup(src, mapping, mr.MatchingOptions())
    assert dedup.summary["skipped_oversized_buckets"] >= 1
    assert dedup.summary["cluster_count"] == 4

    match = mr.run_cross_system_match(src, src, mapping, mapping, mr.MatchingOptions())
    assert match.scorecard["skipped_oversized_buckets"] >= 1
    # Only same-row links via unique address keys survive; the shared company bucket linked nothing across rows.
    assert match.pairs and all(p.left_idx == p.right_idx for p in match.pairs)


def test_query_pairs_pages_before_building_rows(tmp_path: Path) -> None:
    left = [
        ["Alpha Capital LLC", "1 Oak St", "Dallas", "TX", "75201"],
        ["Beta Wealth Inc", "2 Elm St", "Austin", "TX", "78701"],
        ["Zeta Holdings", "9 Pine St", "Reno", "NV", "89501"],
        ["Zulu Partners", "8 Fir St", "Reno", "NV", "89502"],
    ]
    right = left[:2]
    session = mr.run_cross_system_match(
        _csv(tmp_path / "l.csv", left),
        _csv(tmp_path / "r.csv", right),
        _mapping(left),
        _mapping(right),
        mr.MatchingOptions(),
    )
    page = session.query_pairs(view="all_pairs", offset=1, limit=1)
    assert page["total"] == len(session.pairs) >= 2 and len(page["items"]) == 1

    unmatched = session.query_pairs(view="unmatched_left", offset=1, limit=1)
    expected = len(session.left_records) - len(session.matched_left_set)
    assert unmatched["total"] == expected >= 2 and len(unmatched["items"]) == 1
    assert session.query_pairs(view="unmatched_left", search="zeta")["total"] == 1


def test_eviction_deletes_only_files_inside_workbench_root(tmp_path: Path) -> None:
    ws = WorkbenchWorkspace(root_dir=tmp_path / "wb", max_items=1)
    ws.jobs_dir.mkdir(parents=True)
    mine = tmp_path / "mine.csv"
    mine.write_text("a\n", encoding="utf-8")
    temp = ws.jobs_dir / "t.csv"
    temp.write_text("a\n", encoding="utf-8")
    spec = FileFormatSpec(format="csv")

    ws._put_bounded(ws.artifacts, "user", (mine, spec, "m.csv"), unlink_path=True)
    ws._put_bounded(ws.artifacts, "tmp", (temp, spec, "t.csv"), unlink_path=True)  # evicts the user's file entry
    assert mine.exists()
    ws._put_bounded(ws.artifacts, "next", (tmp_path / "gone.csv", spec, "n.csv"), unlink_path=True)  # evicts temp
    assert not temp.exists()


def test_sessions_use_a_smaller_cap_than_files(tmp_path: Path) -> None:
    ws = WorkbenchWorkspace(root_dir=tmp_path / "wb")
    assert ws.max_items == 48 and ws.max_sessions == 8
    for i in range(10):
        ws._put_bounded(ws.match_sessions, f"m{i}", object(), limit=ws.max_sessions)
    assert list(ws.match_sessions) == [f"m{i}" for i in range(2, 10)]


def test_host_guard_and_early_upload_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ENTITY_STANDARDIZER_WORKBENCH_DIR", str(tmp_path / "wb"))
    monkeypatch.delenv("ENTITY_STANDARDIZER_API_KEYS", raising=False)
    monkeypatch.setenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS", "1")
    client = TestClient(create_app(), base_url="http://localhost")

    assert client.get("/ui").status_code == 200
    assert client.get("/ui", headers={"host": "127.0.0.1:8000"}).status_code == 200
    assert client.get("/ui", headers={"host": "[::1]:8000"}).status_code == 200
    assert client.get("/ui", headers={"host": "rebind.evil.example"}).status_code == 403
    monkeypatch.setenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS", "0")
    assert client.get("/ui", headers={"host": "rebind.evil.example"}).status_code == 200

    monkeypatch.setenv("ENTITY_STANDARDIZER_MAX_UPLOAD_MB", "0")
    big = b"a,b\n" + b"x,y\n" * 300_000
    assert client.post("/ui/api/upload", files={"file": ("big.csv", big)}).status_code == 413
    assert not (tmp_path / "wb" / "uploads").exists()  # refused before the handler ran


def test_xlsx_exports_keep_equals_cells_as_text(tmp_path: Path) -> None:
    spec = FileFormatSpec(format="xlsx")
    plain = tmp_path / "plain.xlsx"
    write_tabular_output(plain, ["a", "b"], [{"a": "=1+1", "b": "ok"}], spec)
    templ = tmp_path / "templ.xlsx"
    write_tabular_output(templ, ["a", "b"], [{"a": "=2+2", "b": "ok"}], spec, template_xlsx_path=plain)
    multi = tmp_path / "multi.xlsx"
    write_xlsx_sheets(multi, {"S": (["a"], iter([{"a": "=3+3"}]))})

    for path, text in ((plain, "=1+1"), (templ, "=2+2"), (multi, "=3+3")):
        wb = openpyxl.load_workbook(path)
        cell = wb.worksheets[0]["A2"]
        assert (cell.data_type, cell.value) == ("s", text)
        wb.close()


def test_xlsx_that_expands_too_far_is_rejected(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "small.xlsx"
    wb = openpyxl.Workbook()
    wb.save(path)
    monkeypatch.setattr(io_formats, "_MAX_XLSX_UNPACKED_BYTES", 1)
    with pytest.raises(ValueError, match="expand"):
        io_formats._open_xlsx_workbook(path, read_only=True)


def test_compose_file_is_loopback_only_and_requires_api_keys() -> None:
    compose = (REPO / "docker-compose.service.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8000:8000"' in compose
    assert "ENTITY_STANDARDIZER_API_KEYS: ${ENTITY_STANDARDIZER_API_KEYS:?" in compose
