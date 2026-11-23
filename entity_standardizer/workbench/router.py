"""FastAPI router and workspace management for the Entity Standardizer Web Workbench."""

from __future__ import annotations

from collections import OrderedDict
import ipaddress
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from entity_standardizer import __version__
from entity_standardizer._native_dispatch import is_native_available
from entity_standardizer.identifiers import standardize_crd, standardize_external_id
from entity_standardizer.joint import standardize_contact
from entity_standardizer.scoring import explain_and_score_entities
from entity_standardizer.workbench.io_formats import (
    FileFormatSpec,
    SupportedFormat,
    cell_to_input_text,
    inspect_tabular_source,
)
from entity_standardizer.workbench.mapping import (
    FieldRole,
    MappingConfig,
    PresetStore,
    auto_detect_mappings,
)
from entity_standardizer.workbench.match_runner import (
    ALL_MATCH_SIGNALS,
    DedupSession,
    MatchingOptions,
    MatchSession,
    MemberRosterSource,
    run_cross_system_match,
    run_single_file_dedup,
)
from entity_standardizer.workbench.options import StandardizationOptions
from entity_standardizer.workbench.standardize_runner import (
    preview_standardize_source,
    standardize_tabular_file,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
_STATIC_ASSETS: dict[str, str] = {
    "styles.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
}

_CONTACT_KWARGS: frozenset[str] = frozenset(
    {
        "street1",
        "street2",
        "city",
        "state",
        "postal_code",
        "country",
        "phone",
        "fax",
        "organization",
        "person_name",
        "job_title",
        "email",
        "website",
        "social",
    }
)


def is_local_paths_enabled() -> bool:
    """Return True when zero-copy local disk file paths are permitted via environment config."""
    return os.environ.get("ENTITY_STANDARDIZER_ALLOW_LOCAL_PATHS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def max_upload_bytes() -> int:
    """Return the per-file upload limit in bytes (ENTITY_STANDARDIZER_MAX_UPLOAD_MB, default 512)."""
    return int(float(os.environ.get("ENTITY_STANDARDIZER_MAX_UPLOAD_MB", "512")) * 1024 * 1024)


def _require_safe_host(request: Request) -> None:
    """Reject name-based Host headers (DNS rebinding) while local disk paths are enabled.

    A rebinding page reaches this server under its own hostname; IP literals and ``localhost`` cannot be rebound.
    """
    if not is_local_paths_enabled():
        return
    host = request.url.hostname or ""
    if host == "localhost":
        return
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise HTTPException(status_code=403, detail="Host header not allowed while local disk paths are enabled.") from None


class InspectPathRequest(BaseModel):
    """Request payload for /ui/api/inspect-path."""

    path: str = Field(..., description="Absolute or workspace-relative file path on local disk.")
    delimiter: str | None = Field(default=None, description="Optional delimiter override for text files.")
    sheet_name: str | None = Field(default=None, description="Optional Excel worksheet name.")


class ReinspectRequest(BaseModel):
    """Request payload for /ui/api/reinspect."""

    source_id: str = Field(..., description="Registered uploaded or local source identifier.")
    delimiter: str | None = Field(default=None, description="Updated delimiter override.")
    sheet_name: str | None = Field(default=None, description="Updated Excel worksheet name.")


class PresetSaveRequest(BaseModel):
    """Request payload for saving a field mapping and options preset."""

    name: str = Field(..., description="Preset name.")
    description: str = Field(default="", description="Optional preset description.")
    mapping_config: dict[str, Any] = Field(default_factory=dict)
    standardize_options: dict[str, Any] = Field(default_factory=dict)
    matching_options: dict[str, Any] = Field(default_factory=dict)


class StandardizePreviewRequest(BaseModel):
    """Request payload for dry-run file standardization preview."""

    source_id: str = Field(..., description="Source identifier.")
    mapping_config: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=50, ge=1, le=200)


class StandardizeRunRequest(BaseModel):
    """Request payload for running full file standardization."""

    source_id: str = Field(..., description="Source identifier.")
    mapping_config: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    output_path: str | None = Field(default=None, description="Optional local disk destination path.")


class RosterAttachPayload(BaseModel):
    """Configuration for attaching a child member roster file to Left or Right records."""

    source_id: str = Field(..., description="Uploaded or local source_id of child member table.")
    parent_id_col: str = Field(..., description="Column holding parent entity ID.")
    member_cols: list[str] = Field(..., min_length=1, description="Column(s) holding member CRDs/names/emails.")


class MatchRunRequest(BaseModel):
    """Request payload for running a two-file cross-system match."""

    left_source_id: str
    right_source_id: str
    left_mapping: dict[str, Any] = Field(default_factory=dict)
    right_mapping: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    left_roster: RosterAttachPayload | None = None
    right_roster: RosterAttachPayload | None = None


class MatchDecisionRequest(BaseModel):
    """Request payload for steward match pair approve/reject/reset override."""

    pair_id: str
    decision: str = Field(..., description="One of 'approve', 'reject', or 'reset'.")
    note: str = Field(default="")


class DedupRunRequest(BaseModel):
    """Request payload for running single-file deduplication."""

    source_id: str
    mapping_config: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)


class DedupOverrideRequest(BaseModel):
    """Request payload for excluding or restoring a row from single-file deduplication clusters."""

    row_index: int
    excluded: bool


class LiveInspectRequest(BaseModel):
    """Request payload for Live Inspector single-entity or pairwise comparison sandbox."""

    mode: str = Field(default="single", description="'single' or 'compare'.")
    entity_a: dict[str, Any] = Field(default_factory=dict)
    entity_b: dict[str, Any] | None = Field(default=None)
    default_country: str = Field(default="US")


class _RegisteredSource:
    __slots__ = ("source_id", "path", "original_name", "delimiter", "sheet_name", "is_upload")

    def __init__(
        self,
        source_id: str,
        path: Path,
        original_name: str,
        delimiter: str | None = None,
        sheet_name: str | None = None,
        is_upload: bool = False,
    ) -> None:
        self.source_id = source_id
        self.path = path
        self.original_name = original_name
        self.delimiter = delimiter
        self.sheet_name = sheet_name
        self.is_upload = is_upload


class WorkbenchWorkspace:
    """Bounded temporary storage for uploaded sources, standardized artifacts, and match sessions."""

    def __init__(self, root_dir: str | Path | None = None, max_items: int = 48) -> None:
        base = (
            Path(root_dir)
            if root_dir is not None
            else Path(
                os.environ.get("ENTITY_STANDARDIZER_WORKBENCH_DIR")
                or (Path(tempfile.gettempdir()) / "entity_standardizer_workbench")
            )
        )
        self.root_dir = base
        self.uploads_dir = base / "uploads"
        self.jobs_dir = base / "jobs"
        self.max_items = max_items
        # Sessions hold every pair and display row of a run, so keep far fewer of them than file handles.
        # State is per process: run the workbench with a single uvicorn worker.
        self.max_sessions = min(max_items, 8)
        self.sources: OrderedDict[str, _RegisteredSource] = OrderedDict()
        self.artifacts: OrderedDict[str, tuple[Path, FileFormatSpec, str]] = OrderedDict()
        self.match_sessions: OrderedDict[str, MatchSession] = OrderedDict()
        self.dedup_sessions: OrderedDict[str, DedupSession] = OrderedDict()
        self._lock = threading.RLock()

    def _put_bounded(
        self,
        store: OrderedDict[str, Any],
        key: str,
        value: Any,
        unlink_path: bool = False,
        limit: int | None = None,
    ) -> None:
        """Insert into a bounded store; with unlink_path, evicted entries' files are deleted if the workbench owns them.

        Files outside ``root_dir`` (a user's own source or ``output_path`` target) are never deleted.
        """
        with self._lock:
            store[key] = value
            store.move_to_end(key)
            while len(store) > (limit or self.max_items):
                _, evicted = store.popitem(last=False)
                if unlink_path:
                    cand = Path(evicted.path if isinstance(evicted, _RegisteredSource) else evicted[0])
                    if cand.is_file() and cand.resolve().is_relative_to(self.root_dir.resolve()):
                        cand.unlink()

    def register_source(
        self,
        path: Path,
        original_name: str,
        *,
        delimiter: str | None = None,
        sheet_name: str | None = None,
        is_upload: bool = False,
    ) -> _RegisteredSource:
        """Register an uploaded or local disk file source and return its handle."""
        sid = uuid.uuid4().hex[:12]
        src = _RegisteredSource(sid, path, original_name, delimiter, sheet_name, is_upload=is_upload)
        self._put_bounded(self.sources, sid, src, unlink_path=True)
        return src

    def remove_source(self, source_id: str, *, unlink_upload: bool = True) -> None:
        """Unregister a source and optionally remove its uploaded temp file."""
        with self._lock:
            removed = self.sources.pop(source_id, None)
            if unlink_upload and removed is not None and removed.is_upload and removed.path.is_file():
                removed.path.unlink()

    def get_source(self, source_id: str) -> _RegisteredSource:
        """Retrieve a registered source or raise HTTP 404."""
        with self._lock:
            if source_id not in self.sources:
                raise HTTPException(status_code=404, detail=f"Unknown source_id '{source_id}'.")
            return self.sources[source_id]

    def get_artifact(self, job_id: str) -> tuple[Path, FileFormatSpec, str]:
        """Retrieve a generated artifact descriptor or raise HTTP 404."""
        with self._lock:
            if job_id not in self.artifacts:
                raise HTTPException(status_code=404, detail=f"Unknown job_id '{job_id}'.")
            artifact = self.artifacts[job_id]
            if not Path(artifact[0]).is_file():
                self.artifacts.pop(job_id, None)
                raise HTTPException(status_code=404, detail=f"Artifact file for job_id '{job_id}' is no longer available.")
            return artifact

    def get_match_session(self, job_id: str) -> MatchSession:
        """Retrieve a cross-system match session or raise HTTP 404."""
        with self._lock:
            if job_id not in self.match_sessions:
                raise HTTPException(status_code=404, detail=f"Unknown match job_id '{job_id}'.")
            return self.match_sessions[job_id]

    def get_dedup_session(self, job_id: str) -> DedupSession:
        """Retrieve a single-file dedup session or raise HTTP 404."""
        with self._lock:
            if job_id not in self.dedup_sessions:
                raise HTTPException(status_code=404, detail=f"Unknown dedup job_id '{job_id}'.")
            return self.dedup_sessions[job_id]


def _inspect_and_suggest(src: _RegisteredSource) -> dict[str, Any]:
    info = inspect_tabular_source(
        src.path,
        delimiter_override=src.delimiter,
        sheet_name=src.sheet_name,
    )
    suggested = auto_detect_mappings(info["columns"], info["sample_rows"]).to_dict()
    return {"source_id": src.source_id, **info, "file_name": src.original_name, "suggested_mapping": suggested}


def _inspect_registered_source(
    ws: WorkbenchWorkspace,
    src: _RegisteredSource,
    *,
    cleanup_on_error: bool = True,
) -> dict[str, Any]:
    try:
        return _inspect_and_suggest(src)
    except (ValueError, ImportError) as exc:
        if cleanup_on_error:
            ws.remove_source(src.source_id, unlink_upload=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _parse_mapping_and_options(
    mapping_dict: dict[str, Any],
    options_dict: dict[str, Any],
    opts_cls: type[Any],
) -> tuple[MappingConfig, Any]:
    try:
        return MappingConfig.from_dict(mapping_dict), opts_cls.from_dict(options_dict)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_checked(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except (ValueError, ImportError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def create_workbench_router(workspace: WorkbenchWorkspace | None = None) -> APIRouter:
    """Create the FastAPI APIRouter serving the Entity Standardizer Web Workbench UI and /ui/api/*."""
    ws = workspace or WorkbenchWorkspace()
    router = APIRouter(dependencies=[Depends(_require_safe_host)])

    def _preset_store() -> PresetStore:
        return PresetStore()

    @router.get("/ui", include_in_schema=False)
    def workbench_index() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    @router.get("/ui/assets/{asset_name}", include_in_schema=False)
    def workbench_asset(asset_name: str) -> Response:
        if asset_name not in _STATIC_ASSETS:
            raise HTTPException(status_code=404, detail="Asset not found.")
        return Response(
            content=(STATIC_DIR / asset_name).read_text(encoding="utf-8"),
            media_type=_STATIC_ASSETS[asset_name],
        )

    @router.get("/ui/api/capabilities")
    def workbench_capabilities() -> dict[str, Any]:
        return {
            "version": __version__,
            "native_available": is_native_available(),
            "local_paths_enabled": is_local_paths_enabled(),
            "roles": [r.value for r in FieldRole],
            "profiles": ["FIRM", "OFFICE", "CONTACT", "PARTNERSHIP", "TEAM", "CUSTOM"],
            "formats": [f.value for f in SupportedFormat],
            "signals": list(ALL_MATCH_SIGNALS),
            "default_standardize_options": StandardizationOptions().to_dict(),
            "default_matching_options": MatchingOptions().to_dict(),
        }

    @router.post("/ui/api/upload")
    async def workbench_upload(
        file: UploadFile = File(...),
        delimiter: str | None = Form(default=None),
        sheet_name: str | None = Form(default=None),
    ) -> dict[str, Any]:
        ws.uploads_dir.mkdir(parents=True, exist_ok=True)
        raw_name = re.split(r"[\\/]", (file.filename or "upload.csv").split(":", 1)[0])[-1] or "upload.csv"
        raw_sfx = Path(raw_name).suffix
        suffix = raw_sfx if re.match(r"^\.[A-Za-z0-9]{1,12}$", raw_sfx) else ".csv"
        dest = ws.uploads_dir / f"{uuid.uuid4().hex[:12]}{suffix}"
        max_bytes = max_upload_bytes()
        written = 0
        with dest.open("wb") as fout:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    fout.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="Uploaded file exceeds maximum allowed size.")
                fout.write(chunk)
        src = ws.register_source(
            dest, raw_name, delimiter=delimiter or None, sheet_name=sheet_name or None, is_upload=True
        )
        return _inspect_registered_source(ws, src)

    @router.post("/ui/api/inspect-path")
    def workbench_inspect_path(req: InspectPathRequest) -> dict[str, Any]:
        if not is_local_paths_enabled():
            raise HTTPException(status_code=403, detail="Local disk path inspection is disabled on this server.")
        p = Path(req.path)
        try:
            if "\x00" in req.path:
                raise ValueError("Invalid file path.")
            exists_file = p.is_file()
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid file path: {exc}") from exc
        if not exists_file:
            raise HTTPException(status_code=404, detail=f"File not found: '{req.path}'.")
        src = ws.register_source(
            p, p.name, delimiter=req.delimiter or None, sheet_name=req.sheet_name or None, is_upload=False
        )
        return _inspect_registered_source(ws, src)

    @router.post("/ui/api/reinspect")
    def workbench_reinspect(req: ReinspectRequest) -> dict[str, Any]:
        src = ws.get_source(req.source_id)
        old_delim, old_sheet = src.delimiter, src.sheet_name
        src.delimiter = req.delimiter or None
        src.sheet_name = req.sheet_name or None
        try:
            return _inspect_registered_source(ws, src, cleanup_on_error=False)
        except HTTPException:
            src.delimiter, src.sheet_name = old_delim, old_sheet
            raise

    @router.get("/ui/api/presets")
    def workbench_list_presets() -> dict[str, Any]:
        return {"presets": _preset_store().list_presets()}

    @router.post("/ui/api/presets")
    def workbench_save_preset(req: PresetSaveRequest) -> dict[str, Any]:
        try:
            saved = _preset_store().save_preset(req.name, req.model_dump())
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return saved

    @router.get("/ui/api/presets/{name}")
    def workbench_get_preset(name: str) -> dict[str, Any]:
        try:
            return _preset_store().get_preset(name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/ui/api/presets/{name}")
    def workbench_delete_preset(name: str) -> dict[str, Any]:
        try:
            deleted = _preset_store().delete_preset(name)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Preset '{name}' not found.")
        return {"deleted": True, "name": name}

    @router.post("/ui/api/standardize/preview")
    def workbench_standardize_preview(req: StandardizePreviewRequest) -> dict[str, Any]:
        src = ws.get_source(req.source_id)
        mapping, options = _parse_mapping_and_options(req.mapping_config, req.options, StandardizationOptions)
        return _run_checked(
            preview_standardize_source,
            src.path,
            mapping,
            options,
            limit=req.limit,
            delimiter_override=src.delimiter,
            sheet_name=src.sheet_name,
        )

    @router.post("/ui/api/standardize/run")
    def workbench_standardize_run(req: StandardizeRunRequest) -> dict[str, Any]:
        src = ws.get_source(req.source_id)
        mapping, options = _parse_mapping_and_options(req.mapping_config, req.options, StandardizationOptions)
        ws.jobs_dir.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex[:12]

        if req.output_path:
            if not is_local_paths_enabled():
                raise HTTPException(status_code=403, detail="Local disk path export is disabled on this server.")
            if "\x00" in req.output_path or Path(req.output_path).is_dir():
                raise HTTPException(status_code=400, detail="output_path must be a valid file path, not a directory.")
            dest = Path(req.output_path)
        else:
            stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(src.original_name).stem).strip("._") or "output"
            suffix = src.path.suffix or ".csv"
            dest = ws.jobs_dir / f"{job_id}_{stem}_standardized{suffix}"

        summary = _run_checked(
            standardize_tabular_file,
            src.path,
            dest,
            mapping,
            options,
            delimiter_override=src.delimiter,
            sheet_name=src.sheet_name,
        )
        spec = FileFormatSpec.from_dict(summary["format_spec"])
        out_name = f"{Path(src.original_name).stem}_standardized{spec.extension_for_export()}"
        ws._put_bounded(ws.artifacts, job_id, (dest, spec, out_name), unlink_path=True)
        return {
            **summary,
            "job_id": job_id,
            "download_url": f"/ui/api/jobs/{job_id}/download",
            "download_filename": out_name,
            "output_path": summary["output_path"] if req.output_path else None,
        }

    @router.get("/ui/api/jobs/{job_id}/download")
    def workbench_download_job(job_id: str) -> FileResponse:
        dest, spec, filename = ws.get_artifact(job_id)
        return FileResponse(path=str(dest), media_type=spec.media_type(), filename=filename)

    def _build_roster_src(payload: RosterAttachPayload | None) -> MemberRosterSource | None:
        if payload is None:
            return None
        r_src = ws.get_source(payload.source_id)
        return MemberRosterSource(
            path=r_src.path,
            parent_id_col=payload.parent_id_col,
            member_cols=payload.member_cols,
            delimiter_override=r_src.delimiter,
            sheet_name=r_src.sheet_name,
        )

    @router.post("/ui/api/match/run")
    def workbench_match_run(req: MatchRunRequest) -> dict[str, Any]:
        l_src = ws.get_source(req.left_source_id)
        r_src = ws.get_source(req.right_source_id)
        l_map, match_opts = _parse_mapping_and_options(req.left_mapping, req.options, MatchingOptions)
        r_map, _ = _parse_mapping_and_options(req.right_mapping, req.options, MatchingOptions)
        session = _run_checked(
            run_cross_system_match,
            l_src.path,
            r_src.path,
            l_map,
            r_map,
            match_opts,
            left_delimiter=l_src.delimiter,
            left_sheet=l_src.sheet_name,
            right_delimiter=r_src.delimiter,
            right_sheet=r_src.sheet_name,
            left_roster_source=_build_roster_src(req.left_roster),
            right_roster_source=_build_roster_src(req.right_roster),
        )
        job_id = uuid.uuid4().hex[:12]
        ws._put_bounded(ws.match_sessions, job_id, session, limit=ws.max_sessions)
        return {"job_id": job_id, "scorecard": session.scorecard}

    @router.get("/ui/api/match/{job_id}/pairs")
    def workbench_match_pairs(
        job_id: str,
        view: str = Query(default="all_pairs"),
        cardinality: str | None = Query(default=None),
        search: str = Query(default=""),
        discrepancy_only: bool = Query(default=False),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        session = ws.get_match_session(job_id)
        return session.query_pairs(
            view=view,
            cardinality=cardinality or None,
            search=search,
            discrepancy_only=discrepancy_only,
            offset=offset,
            limit=limit,
        )

    @router.post("/ui/api/match/{job_id}/decision")
    def workbench_match_decision(job_id: str, req: MatchDecisionRequest) -> dict[str, Any]:
        session = ws.get_match_session(job_id)
        try:
            return session.apply_decision(req.pair_id, req.decision, note=req.note)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/ui/api/match/{job_id}/export")
    def workbench_match_export(
        job_id: str,
        artifact: str = Query(default="comparison"),
        format: str | None = Query(default=None),
    ) -> FileResponse:
        session = ws.get_match_session(job_id)
        ws.jobs_dir.mkdir(parents=True, exist_ok=True)
        exp_id = uuid.uuid4().hex[:10]

        def _finish(dest: Path, spec: FileFormatSpec, filename: str) -> FileResponse:
            ws._put_bounded(ws.artifacts, exp_id, (dest, spec, filename), unlink_path=True)
            return FileResponse(path=str(dest), media_type=spec.media_type(), filename=filename)

        if artifact == "xlsx_bundle":
            spec = FileFormatSpec(format=SupportedFormat.XLSX.value)
            dest = ws.jobs_dir / f"{job_id}_{exp_id}_match_bundle.xlsx"
            _run_checked(session.export_xlsx_bundle, dest)
            return _finish(dest, spec, "match_bundle.xlsx")

        if artifact == "enriched_left":
            spec = session.left_format
            ext = spec.extension_for_export()
            dest = ws.jobs_dir / f"{job_id}_{exp_id}_enriched_left{ext}"
            _run_checked(session.export_enriched_left, dest)
            return _finish(dest, spec, f"enriched_left{ext}")

        if artifact == "unmatched_left":
            spec = session.left_format
            ext = spec.extension_for_export()
            dest = ws.jobs_dir / f"{job_id}_{exp_id}_unmatched_left{ext}"
            _run_checked(session.export_unmatched_left, dest)
            return _finish(dest, spec, f"unmatched_left{ext}")

        if artifact == "unmatched_right":
            spec = session.right_format
            ext = spec.extension_for_export()
            dest = ws.jobs_dir / f"{job_id}_{exp_id}_unmatched_right{ext}"
            _run_checked(session.export_unmatched_right, dest)
            return _finish(dest, spec, f"unmatched_right{ext}")

        if artifact not in ("comparison", "scorecard"):
            raise HTTPException(status_code=400, detail=f"Unknown export artifact '{artifact}'.")

        try:
            fmt_val = SupportedFormat((format or SupportedFormat.CSV.value).lower()).value
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unsupported export format '{format}'.") from exc

        spec = FileFormatSpec(format=fmt_val)
        ext = spec.extension_for_export()
        dest = ws.jobs_dir / f"{job_id}_{exp_id}_{artifact}{ext}"
        _run_checked(session.export_comparison if artifact == "comparison" else session.export_scorecard, dest, spec)
        return _finish(dest, spec, f"{artifact}{ext}")

    @router.post("/ui/api/dedup/run")
    def workbench_dedup_run(req: DedupRunRequest) -> dict[str, Any]:
        src = ws.get_source(req.source_id)
        mapping, match_opts = _parse_mapping_and_options(req.mapping_config, req.options, MatchingOptions)
        session = _run_checked(
            run_single_file_dedup,
            src.path,
            mapping,
            match_opts,
            delimiter_override=src.delimiter,
            sheet_name=src.sheet_name,
        )
        job_id = uuid.uuid4().hex[:12]
        ws._put_bounded(ws.dedup_sessions, job_id, session, limit=ws.max_sessions)
        return {"job_id": job_id, "summary": session.summary, "clusters": session.clusters[:100]}

    @router.get("/ui/api/dedup/{job_id}/clusters")
    def workbench_dedup_clusters(
        job_id: str,
        multi_only: bool = Query(default=False),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        session = ws.get_dedup_session(job_id)
        with session._lock:
            items = [
                c
                for c in session.clusters
                if (c["cluster_size"] > 1 or any(m["excluded"] for m in c["members"]) if multi_only else True)
            ]
            summary = dict(session.summary)
        return {
            "total": len(items),
            "summary": summary,
            "clusters": items[offset : offset + limit],
        }

    @router.post("/ui/api/dedup/{job_id}/override")
    def workbench_dedup_override(job_id: str, req: DedupOverrideRequest) -> dict[str, Any]:
        session = ws.get_dedup_session(job_id)
        try:
            return session.set_excluded_row(req.row_index, req.excluded)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/ui/api/dedup/{job_id}/export")
    def workbench_dedup_export(
        job_id: str,
        mode: str = Query(default="tagged_all_rows"),
    ) -> FileResponse:
        session = ws.get_dedup_session(job_id)
        ws.jobs_dir.mkdir(parents=True, exist_ok=True)
        ext = session.format_spec.extension_for_export()
        safe_tag = mode if mode in ("tagged_all_rows", "golden_only") else "invalid"
        exp_id = uuid.uuid4().hex[:10]
        filename = f"deduplicated_{safe_tag}{ext}"
        dest = ws.jobs_dir / f"{job_id}_{exp_id}_{filename}"
        _run_checked(session.export, dest, mode=mode)
        ws._put_bounded(ws.artifacts, exp_id, (dest, session.format_spec, filename), unlink_path=True)
        return FileResponse(
            path=str(dest),
            media_type=session.format_spec.media_type(),
            filename=filename,
        )

    @router.post("/ui/api/live/inspect")
    def workbench_live_inspect(req: LiveInspectRequest) -> dict[str, Any]:
        clean_a = {k: cell_to_input_text(v) or None for k, v in req.entity_a.items() if k in _CONTACT_KWARGS}
        ext_a = cell_to_input_text(req.entity_a.get("external_id")) or None
        crd_a = cell_to_input_text(req.entity_a.get("crd")) or None
        if req.mode == "compare" and req.entity_b is not None:
            clean_b = {k: cell_to_input_text(v) or None for k, v in req.entity_b.items() if k in _CONTACT_KWARGS}
            return explain_and_score_entities(
                standardize_contact(**clean_a, default_country=req.default_country),
                standardize_contact(**clean_b, default_country=req.default_country),
                external_id_a=ext_a,
                external_id_b=cell_to_input_text(req.entity_b.get("external_id")) or None,
                crd_a=crd_a,
                crd_b=cell_to_input_text(req.entity_b.get("crd")) or None,
            ).to_dict()
        out = standardize_contact(**clean_a, default_country=req.default_country).to_dict()
        if crd_a:
            out["crd"] = standardize_crd(crd_a).to_dict()
        if ext_a:
            out["external_id"] = standardize_external_id(ext_a).to_dict()
        return out

    return router
