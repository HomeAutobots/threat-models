"""The GET routes. One Registry call each; every rule lives in tmreg."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from tmreg import config, model
from tmreg.core import Registry, RegistryError

from .registry_dep import db_path, get_registry

router = APIRouter(prefix="/api")

MEDIA = {"md": "text/markdown", "csv": "text/csv", "html": "text/html"}


@router.get("/meta")
async def meta(request: Request):
    project = config.load_project(request.app.state.root)
    return {
        "fields": model.RISK_FIELDS,
        "editable": model.EDITABLE_FIELDS,
        "labels": model.LABELS,
        "stride": model.STRIDE_NAMES,
        "linddun": model.LINDDUN,
        "treatments": model.TREATMENTS,
        "confidence": model.CONFIDENCE,
        "min_lengths": model.MIN_LENGTHS,
        "note_min": model.NOTE_MIN,
        "human_required": model.HUMAN_REQUIRED,
        "ai_required": model.AI_REQUIRED,
        "statuses": [s for s in model.STATUSES if s != "retired"],
        "origins": project.origins,
        "methods": config.METHODS,
    }


@router.get("/{reg}/systems")
async def systems(reg: str, request: Request):
    if not db_path(request.app.state.root, reg).is_file():
        return []
    registry = Registry(request.app.state.root, trial=(reg == "trial"))
    try:
        return registry.list_systems()
    finally:
        registry.close()


@router.get("/{reg}/systems/{slug}/risks")
async def risks(slug: str, state: str = "all", registry: Registry = Depends(get_registry)):
    return registry.list_risks(slug, state)


@router.get("/{reg}/systems/{slug}/risks/{id}")
async def risk_detail(slug: str, id: str, registry: Registry = Depends(get_registry)):
    risk = registry.get_risk(slug, id)
    status = registry.dfd_status(slug)
    error = None
    try:
        details = registry.dfd_details(slug)
    except RegistryError as e:
        details, error = {}, str(e)
    duplicate = risk.get("possible_duplicate_of")
    return {
        "risk": risk,
        "elements": {e: details.get(e) for e in risk["elements"] or ()},
        "dfd": {
            "state": status.state,
            "latest_id": status.latest["id"] if status.latest else None,
            "written_against": risk["dfd_approval_id"],
            "error": error,
        },
        "editors_since_approval": registry.editors(slug, id, since_last_approval=True),
        "duplicate": registry.get_risk(slug, duplicate) if duplicate else None,
    }


@router.get("/{reg}/systems/{slug}/risks/{id}/history")
async def risk_history(slug: str, id: str, registry: Registry = Depends(get_registry)):
    return registry.history(slug, id)


@router.get("/{reg}/systems/{slug}/history")
async def system_history(slug: str, registry: Registry = Depends(get_registry)):
    return registry.history(slug)


@router.get("/{reg}/systems/{slug}/verify")
async def verify(slug: str, registry: Registry = Depends(get_registry)):
    return {"problems": registry.verify(slug)}


@router.get("/{reg}/systems/{slug}/dfd")
async def dfd(slug: str, registry: Registry = Depends(get_registry)):
    status = registry.dfd_status(slug)
    approvals = registry.dfd_approvals(slug)
    preview = error = None
    try:
        p = registry.dfd_preview(slug)
        parsed = p["dfd"]
        preview = {"version": parsed.version, "sha256": parsed.sha256, "ids": parsed.ids,
                   "details": parsed.details, "added": p["added"], "removed": p["removed"],
                   "warnings": p["warnings"]}
    except RegistryError as e:
        error = str(e)
    path = registry.root / "systems" / slug / "dfd.md"
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        text = None
    return {
        "status": {"state": status.state, "latest": status.latest,
                   "current_sha256": status.current_sha256},
        "approvals": approvals,
        "preview": preview,
        "preview_error": error,
        "text": text,
    }


@router.get("/{reg}/systems/{slug}/report")
async def report(slug: str, format: str = "md", include_pending: bool = False,
                 include_rejected: bool = False, include_retired: bool = False,
                 download: bool = False, registry: Registry = Depends(get_registry)):
    text = registry.report(slug, format, include_pending=include_pending,
                           include_retired=include_retired, include_rejected=include_rejected)
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{slug}-register.{format}"'
    return Response(text, media_type=MEDIA[format], headers=headers)
