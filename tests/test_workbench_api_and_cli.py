"""Tests for FastAPI Web Workbench (/ui & /ui/api/*) endpoints, security guards, and CLI `ui`."""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from entity_standardizer.cli import main as cli_main
from entity_standardizer.server import create_app
from entity_standardizer.workbench.router import WorkbenchWorkspace


def test_workbench_ui_api_workflows_and_security(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ENTITY_STANDARDIZER_WORKBENCH_DIR", str(tmp_path / "wb"))
    monkeypatch.setenv("ENTITY_STANDARDIZER_PRESETS_DIR", str(tmp_path / "presets"))
    monkeypatch.delenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS", raising=False)
    monkeypatch.delenv("ENTITY_STANDARDIZER_API_KEYS", raising=False)

    app = create_app()
    client = TestClient(app)

    # 1. Static UI HTML, CSS, JS, and 404 on unknown asset
    r_idx = client.get("/ui")
    assert r_idx.status_code == 200 and "Entity Standardizer Workbench" in r_idx.text
    assert client.get("/ui/assets/styles.css").status_code == 200
    assert client.get("/ui/assets/app.js").status_code == 200
    assert client.get("/ui/assets/missing.js").status_code == 404

    # 2. Capabilities (local_paths_enabled=False by default)
    r_caps = client.get("/ui/api/capabilities")
    assert r_caps.status_code == 200 and r_caps.json()["local_paths_enabled"] is False

    # 3. API Key authentication enforcement on /ui/api/* while /ui HTML stays reachable
    monkeypatch.setenv("ENTITY_STANDARDIZER_API_KEYS", "wb-secret")
    assert client.get("/ui").status_code == 200
    assert client.get("/ui/api/capabilities").status_code == 401
    assert client.get("/ui/api/capabilities", headers={"X-API-Key": "wb-secret"}).status_code == 200
    monkeypatch.delenv("ENTITY_STANDARDIZER_API_KEYS")

    # 4. Local path guard (403 when disabled, 200/404 when enabled)
    sample_csv = tmp_path / "sample.csv"
    sample_csv.write_text("id,org,phone,email\n1,Acme Inc,212-555-2368,bob@gmial.com\n", encoding="utf-8")
    assert client.post("/ui/api/inspect-path", json={"path": str(sample_csv)}).status_code == 403

    monkeypatch.setenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS", "1")
    assert client.post("/ui/api/inspect-path", json={"path": str(tmp_path / "missing.csv")}).status_code == 404
    r_loc = client.post("/ui/api/inspect-path", json={"path": str(sample_csv)})
    assert r_loc.status_code == 200
    loc_sid = r_loc.json()["source_id"]

    # 5. Multipart upload + reinspect + 404 on unknown source
    r_up = client.post(
        "/ui/api/upload",
        files={"file": ("contacts.csv", b"id,org,phone,email\n1,Acme Inc,212-555-2368,a@gmial.com\n", "text/csv")},
    )
    assert r_up.status_code == 200
    up_sid = r_up.json()["source_id"]
    mapping_cfg = r_up.json()["suggested_mapping"]

    r_rein = client.post("/ui/api/reinspect", json={"source_id": up_sid, "delimiter": ","})
    assert r_rein.status_code == 200
    assert client.post("/ui/api/reinspect", json={"source_id": "bad_id"}).status_code == 404
    # Invalid delimiter on reinspect returns 400 and preserves prior source + uploaded file
    r_rein_bad = client.post("/ui/api/reinspect", json={"source_id": up_sid, "delimiter": "::"})
    assert r_rein_bad.status_code == 400
    assert client.post(
        "/ui/api/standardize/preview",
        json={"source_id": up_sid, "mapping_config": mapping_cfg, "options": {}},
    ).status_code == 200

    # 6. Presets CRUD & error paths
    assert client.get("/ui/api/presets").json()["presets"] == []
    assert client.post("/ui/api/presets", json={"name": "../bad", "mapping_config": {}}).status_code == 400
    assert client.post("/ui/api/presets", json={"name": "Default Map", "mapping_config": mapping_cfg}).status_code == 200
    assert len(client.get("/ui/api/presets").json()["presets"]) == 1
    assert client.get("/ui/api/presets/Default Map").status_code == 200
    (tmp_path / "presets" / "BrokenPreset.json").write_text("{bad", encoding="utf-8")
    assert client.get("/ui/api/presets/BrokenPreset").status_code == 400
    (tmp_path / "presets" / "BrokenPreset.json").unlink()
    assert client.get("/ui/api/presets/NoSuch").status_code == 404
    assert client.get("/ui/api/presets/..bad").status_code == 400
    assert client.delete("/ui/api/presets/Default Map").status_code == 200
    assert client.delete("/ui/api/presets/Default Map").status_code == 404
    assert client.delete("/ui/api/presets/..bad").status_code == 400

    # 7. Standardize preview, download run, local-path run, and 403/404 checks
    r_prev = client.post(
        "/ui/api/standardize/preview",
        json={"source_id": up_sid, "mapping_config": mapping_cfg, "options": {}},
    )
    assert r_prev.status_code == 200 and r_prev.json()["preview_count"] == 1

    r_run = client.post(
        "/ui/api/standardize/run",
        json={"source_id": up_sid, "mapping_config": mapping_cfg, "options": {}},
    )
    assert r_run.status_code == 200 and r_run.json()["output_path"] is None
    dl_url = r_run.json()["download_url"]
    r_dl = client.get(dl_url)
    assert r_dl.status_code == 200 and "+12125552368" in r_dl.text
    assert client.get("/ui/api/jobs/unknown/download").status_code == 404

    # Invalid options / bad JSON upload / size limit return structured HTTP 400/413 errors
    assert (
        client.post(
            "/ui/api/standardize/preview",
            json={"source_id": up_sid, "mapping_config": mapping_cfg, "options": {"column_mode": "bad_mode"}},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/ui/api/upload",
            files={"file": ("bad.json", b'{"not_a_list": 1}', "application/json")},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/ui/api/upload",
            files={"file": ("bad.xlsx", b"not-an-xlsx", "application/octet-stream")},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/ui/api/upload",
            files={"file": ("mid.jsonl", b'{"org": "Acme"}\n123\n', "application/x-ndjson")},
        ).status_code
        == 400
    )
    mid_loc = tmp_path / "mid_local.jsonl"
    mid_loc.write_text('{"org": "Acme"}\n', encoding="utf-8")
    monkeypatch.setenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS", "1")
    r_mid = client.post("/ui/api/inspect-path", json={"path": str(mid_loc)})
    assert r_mid.status_code == 200
    mid_loc.write_text('{"org": "Acme"}\n123\n', encoding="utf-8")
    assert (
        client.post(
            "/ui/api/standardize/run",
            json={
                "source_id": r_mid.json()["source_id"],
                "mapping_config": r_mid.json()["suggested_mapping"],
                "options": {},
            },
        ).status_code
        == 400
    )
    monkeypatch.setenv("ENTITY_STANDARDIZER_MAX_UPLOAD_MB", "0.00001")
    assert (
        client.post(
            "/ui/api/upload",
            files={"file": ("big.csv", b"a,b\n" + b"1,2\n" * 50, "text/csv")},
        ).status_code
        == 413
    )
    monkeypatch.delenv("ENTITY_STANDARDIZER_MAX_UPLOAD_MB")

    out_local = tmp_path / "local_std.csv"
    r_run_loc = client.post(
        "/ui/api/standardize/run",
        json={"source_id": loc_sid, "mapping_config": mapping_cfg, "output_path": str(out_local)},
    )
    assert r_run_loc.status_code == 200 and out_local.is_file()

    monkeypatch.setenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS", "0")
    assert (
        client.post(
            "/ui/api/standardize/run",
            json={"source_id": up_sid, "mapping_config": mapping_cfg, "output_path": str(out_local)},
        ).status_code
        == 403
    )

    # 8. Match run + pairs + decision + all exports (with optional roster)
    r_left = client.post(
        "/ui/api/upload",
        files={"file": ("left.csv", b"id,org,phone,email\nL1,Acme Inc,212-555-2368,a@acme.com\nL2,Beta Co,,b@beta.com\n", "text/csv")},
    )
    r_right = client.post(
        "/ui/api/upload",
        files={"file": ("right.csv", b"id,org,phone,email\nR1,Acme Incorporated,+12125552368,a@acme.com\n", "text/csv")},
    )
    r_rost = client.post(
        "/ui/api/upload",
        files={"file": ("roster.csv", b"pid,rep\nL1,Alice Smith\n", "text/csv")},
    )
    l_data, r_data = r_left.json(), r_right.json()
    m_res = client.post(
        "/ui/api/match/run",
        json={
            "left_source_id": l_data["source_id"],
            "right_source_id": r_data["source_id"],
            "left_mapping": l_data["suggested_mapping"],
            "right_mapping": r_data["suggested_mapping"],
            "options": {"profile": "CONTACT"},
            "left_roster": {
                "source_id": r_rost.json()["source_id"],
                "parent_id_col": "pid",
                "member_cols": ["rep"],
            },
        },
    )
    assert m_res.status_code == 200
    m_job = m_res.json()["job_id"]
    r_pairs = client.get(f"/ui/api/match/{m_job}/pairs")
    assert r_pairs.status_code == 200 and r_pairs.json()["total"] == 1
    pid = r_pairs.json()["items"][0]["pair_id"]

    assert client.post(f"/ui/api/match/{m_job}/decision", json={"pair_id": pid, "decision": "reject"}).status_code == 200
    assert client.post(f"/ui/api/match/{m_job}/decision", json={"pair_id": "bad", "decision": "approve"}).status_code == 404
    assert client.post(f"/ui/api/match/{m_job}/decision", json={"pair_id": pid, "decision": "bad"}).status_code == 400
    assert client.get("/ui/api/match/unknown/pairs").status_code == 404

    for art in ("comparison", "enriched_left", "unmatched_left", "unmatched_right", "scorecard", "xlsx_bundle"):
        r_exp = client.get(f"/ui/api/match/{m_job}/export?artifact={art}&format=csv")
        assert r_exp.status_code == 200
    assert client.get(f"/ui/api/match/{m_job}/export?artifact=bad_art").status_code == 400
    assert client.get(f"/ui/api/match/{m_job}/export?artifact=comparison&format=bad_fmt").status_code == 400

    # 9. Dedup endpoints
    r_d_up = client.post(
        "/ui/api/upload",
        files={"file": ("dedup.csv", b"id,org,phone\n1,Acme Inc,212-555-2368\n2,Acme Incorporated,+12125552368\n", "text/csv")},
    )
    d_info = r_d_up.json()
    d_run = client.post(
        "/ui/api/dedup/run",
        json={"source_id": d_info["source_id"], "mapping_config": d_info["suggested_mapping"], "options": {}},
    )
    assert d_run.status_code == 200
    d_job = d_run.json()["job_id"]
    assert client.get(f"/ui/api/dedup/{d_job}/clusters?multi_only=true").status_code == 200
    assert client.post(f"/ui/api/dedup/{d_job}/override", json={"row_index": 1, "excluded": True}).status_code == 200
    # Excluded row stays visible in multi_only=true so steward can restore it
    assert client.get(f"/ui/api/dedup/{d_job}/clusters?multi_only=true").json()["total"] == 1
    assert client.post(f"/ui/api/dedup/{d_job}/override", json={"row_index": 99, "excluded": True}).status_code == 404
    assert client.get(f"/ui/api/dedup/{d_job}/export?mode=tagged_all_rows").status_code == 200
    assert client.get(f"/ui/api/dedup/{d_job}/export?mode=bad").status_code == 400
    assert client.get("/ui/api/dedup/unknown/clusters").status_code == 404

    # 10. Live inspector (single with and without CRD/external_id, and compare with default_country)
    r_live_plain = client.post(
        "/ui/api/live/inspect",
        json={"mode": "single", "entity_a": {"street1": "350 Fifth Ave", "city": "New York"}},
    )
    assert r_live_plain.status_code == 200 and "crd" not in r_live_plain.json()

    r_live1 = client.post(
        "/ui/api/live/inspect",
        json={
            "mode": "single",
            "entity_a": {
                "street1": "350 Fifth Ave Tel: 555-2368",
                "city": "New York",
                "postal_code": "10118",
                "crd": "CRD# 12345",
                "external_id": "EXT-42",
            },
        },
    )
    assert r_live1.status_code == 200 and r_live1.json()["phone"]["e164"] == "+12125552368"
    assert r_live1.json()["crd"]["canonical_id"] == "12345"
    assert r_live1.json()["external_id"]["canonical_id"] == "EXT-42"

    r_live2 = client.post(
        "/ui/api/live/inspect",
        json={
            "mode": "compare",
            "default_country": "GB",
            "entity_a": {"organization": "Acme UK Ltd", "phone": "020 7946 0018", "email": "sales@acme.co.uk"},
            "entity_b": {"organization": "ACME UK LIMITED", "phone": "+44 20 7946 0018", "email": "sales@acme.co.uk"},
        },
    )
    assert r_live2.status_code == 200 and r_live2.json()["is_match"] is True
    assert "DIRECT_PHONE" in r_live2.json()["matched_signals"]

    # Local bad JSON inspection returns 400 without deleting the source file on disk
    bad_local = tmp_path / "bad_local.json"
    bad_local.write_text('{"no_list": 1}', encoding="utf-8")
    monkeypatch.setenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS", "1")
    assert client.post("/ui/api/inspect-path", json={"path": str(bad_local)}).status_code == 400
    assert bad_local.exists()
    monkeypatch.delenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS")

    # 11. Workspace bounded eviction (upload deleted on eviction, local disk file untouched, unlink_path=False for sessions)
    ws = WorkbenchWorkspace(root_dir=tmp_path / "bounded", max_items=1)
    u1 = tmp_path / "u1.csv"
    u1.write_text("a\n1\n", encoding="utf-8")
    keep_local = tmp_path / "keep.csv"
    keep_local.write_text("a\n2\n", encoding="utf-8")
    ws.register_source(u1, "u1.csv", is_upload=True)
    ws.register_source(keep_local, "keep.csv", is_upload=False)
    s_u3 = ws.register_source(tmp_path / "u3.csv", "u3.csv", is_upload=False)
    assert not u1.exists()
    assert keep_local.exists()
    ws.remove_source(s_u3.source_id, unlink_upload=False)
    ws._put_bounded(ws.match_sessions, "m1", object())
    ws._put_bounded(ws.match_sessions, "m2", object())
    assert list(ws.match_sessions.keys()) == ["m2"]

    # 12. Pass-3 Parquet upload/preview/unmatched strict RFC-8259 JSON (NaN, Inf, bytes, date)
    pq_dirty = tmp_path / "dirty_api.parquet"
    pq.write_table(
        pa.table(
            {
                "id": ["L1"],
                "org": ["Unique Unmatched Alpha LLC"],
                "aum": [float("nan")],
                "inf_v": [float("inf")],
                "as_of": [datetime.date(2026, 3, 1)],
                "raw_b": [b"\x80\x81"],
            }
        ),
        pq_dirty,
    )
    pq_right = tmp_path / "right_api.parquet"
    pq.write_table(
        pa.table({"id": ["R1"], "org": ["Completely Different Beta Inc"]}),
        pq_right,
    )
    with pq_dirty.open("rb") as fl:
        r_pq_up = client.post("/ui/api/upload", files={"file": ("dirty_api.parquet", fl, "application/octet-stream")})
    with pq_right.open("rb") as fr:
        r_right_up = client.post("/ui/api/upload", files={"file": ("right_api.parquet", fr, "application/octet-stream")})
    assert r_pq_up.status_code == 200 and r_right_up.status_code == 200
    r_pq_prev = client.post(
        "/ui/api/standardize/preview",
        json={
            "source_id": r_pq_up.json()["source_id"],
            "mapping_config": r_pq_up.json()["suggested_mapping"],
            "options": {},
        },
    )
    assert r_pq_prev.status_code == 200
    r_pq_match = client.post(
        "/ui/api/match/run",
        json={
            "left_source_id": r_pq_up.json()["source_id"],
            "right_source_id": r_right_up.json()["source_id"],
            "left_mapping": r_pq_up.json()["suggested_mapping"],
            "right_mapping": r_right_up.json()["suggested_mapping"],
            "options": {},
        },
    )
    assert r_pq_match.status_code == 200
    pq_mjob = r_pq_match.json()["job_id"]
    r_unm_l = client.get(f"/ui/api/match/{pq_mjob}/pairs?view=unmatched_left")
    assert r_unm_l.status_code == 200
    for body_txt in (r_pq_up.text, r_pq_prev.text, r_unm_l.text):
        json.loads(
            body_txt,
            parse_constant=lambda bad: (_ for _ in ()).throw(AssertionError(f"Non-RFC8259 token {bad}")),
        )

    # Pass-4: missing optional dependency ImportError cleanly maps to HTTP 400 on upload and export
    def _no_pyarrow():
        raise ImportError("pyarrow is required")

    with monkeypatch.context() as mp:
        mp.setattr("entity_standardizer.workbench.io_formats._ensure_pyarrow", _no_pyarrow)
        with pq_dirty.open("rb") as fl:
            r_no_pa = client.post("/ui/api/upload", files={"file": ("dirty_api.parquet", fl, "application/octet-stream")})
        assert r_no_pa.status_code == 400
        assert client.get(f"/ui/api/match/{pq_mjob}/export?artifact=comparison&format=parquet").status_code == 400

    # 13. Pass-5 API hardening: malformed group_cross_healing (400), ADS/invalid suffix upload (200),
    #     NUL path & directory output_path (400), and numeric JSON values in live/inspect compare (200)
    r_bad_ch = client.post(
        "/ui/api/standardize/preview",
        json={
            "source_id": up_sid,
            "mapping_config": {"mappings": [], "group_cross_healing": [1, 2]},
            "options": {},
        },
    )
    assert r_bad_ch.status_code == 400

    for risky_name in ("evil.csv:ads", "weird.bad?ext"):
        r_risky = client.post(
            "/ui/api/upload",
            files={"file": (risky_name, b"id,org\n1,Acme LLC\n", "text/csv")},
        )
        assert r_risky.status_code == 200

    monkeypatch.setenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS", "1")
    assert client.post("/ui/api/inspect-path", json={"path": "bad\x00.csv"}).status_code == 400
    out_dir = tmp_path / "existing_dir"
    out_dir.mkdir()
    r_dir_out = client.post(
        "/ui/api/standardize/run",
        json={"source_id": up_sid, "mapping_config": {}, "options": {}, "output_path": str(out_dir)},
    )
    assert r_dir_out.status_code == 400
    monkeypatch.delenv("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS")

    r_live_num = client.post(
        "/ui/api/live/inspect",
        json={
            "mode": "compare",
            "entity_a": {"organization": "Acme Corp", "phone": 2125552368, "postal_code": 10118, "crd": 12345},
            "entity_b": {"organization": "ACME CORP", "phone": 2125552368, "crd": 12345},
        },
    )
    assert r_live_num.status_code == 200 and r_live_num.json()["is_match"] is True


def test_cli_ui_command(monkeypatch) -> None:
    import uvicorn
    import webbrowser

    mock_run = MagicMock()
    mock_open = MagicMock()
    monkeypatch.setattr(uvicorn, "run", mock_run)
    monkeypatch.setattr(webbrowser, "open", mock_open)

    rc = cli_main(["ui", "--host", "127.0.0.1", "--port", "9001", "--open"])
    assert rc == 0
    assert os.environ["ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS"] == "1"
    mock_open.assert_called_once_with("http://127.0.0.1:9001/ui")
    mock_run.assert_called_once_with("entity_standardizer.server:app", host="127.0.0.1", port=9001)

    mock_run.reset_mock()
    mock_open.reset_mock()
    rc2 = cli_main(["ui", "--host", "0.0.0.0", "--no-allow-local-paths"])
    assert rc2 == 0
    assert os.environ["ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS"] == "0"
    mock_open.assert_not_called()
    assert SimpleNamespace(called=mock_run.called).called is True

    mock_run.reset_mock()
    mock_open.reset_mock()
    rc3 = cli_main(["ui", "--host", "0.0.0.0", "--port", "8123", "--open", "--allow-local-paths"])
    assert rc3 == 0
    assert os.environ["ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS"] == "1"
    mock_open.assert_called_once_with("http://127.0.0.1:8123/ui")

    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "uvicorn", None)
        assert cli_main(["ui"]) == 1
