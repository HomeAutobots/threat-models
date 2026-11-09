"""The GET routes. One Registry call each; every rule lives in tmreg."""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from tmreg import config, model
from tmreg.core import Registry, RegistryError

from .registry_dep import db_path, get_registry

router = APIRouter(prefix="/api")

def _row(approval: dict | None) -> dict | None:
    """An approval without its record and source (the page gets the record separately)."""
    return None if approval is None else {
        k: v for k, v in approval.items() if k not in ("model", "source")}


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
    status = registry.c4_status(slug)
    basis_id = risk.get("model_approval_id")
    moved = registry.moved_on(slug, risk)
    duplicate = risk.get("possible_duplicate_of")
    return {
        "risk": risk,
        "elements": registry.cited_items(slug, risk),
        "model": {
            "state": status.state,
            "latest_id": status.latest["id"] if status.latest else None,
            "written_against": moved["written_against"],
            "moved_on": moved["moved_on"],
            "changed": moved["changed"],
            "basis": "model" if basis_id else "dfd",
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


def _structurizr_not_checked() -> dict:
    return {"state": "not-checked", "message": None, "base": None, "views": []}


@router.get("/{reg}/systems/{slug}/c4")
async def c4_model(slug: str, registry: Registry = Depends(get_registry)):
    status = registry.c4_status(slug)
    approvals = [_row(a) for a in registry.model_approvals(slug)]
    preview = error = None
    text = ""
    try:
        p = registry.c4_preview(slug)
    except RegistryError as e:  # the sibling register cannot be read
        error = str(e)
    else:
        error, text = p["error"], p["text"]
        if p["model"] is not None:
            preview = {"sha256": p["sha256"], "version": p["model"].version,
                       "ids": p["model"].ids(), "record": p["record"], "added": p["added"],
                       "removed": p["removed"], "changed": p["changed"],
                       "warnings": p["warnings"], "next_ids": p["next_ids"],
                       "reused": p["reused"], "problems": p["problems"], "diff": p["diff"],
                       "adoption": p["adoption"]}
    return {
        "status": {"state": status.state, "latest": _row(status.latest),
                   "current_sha256": status.current_sha256},
        "approvals": approvals,
        "preview": preview,
        "error": error,
        "text": text,
        "counts": registry.open_risk_counts(slug),
        "latest_record": status.latest["model"] if status.latest else None,
        "structurizr": _structurizr_not_checked(),
    }


@router.get("/{reg}/systems/{slug}/c4/routes")
async def c4_routes(slug: str, from_id: str = Query(alias="from"), to_id: str = Query(alias="to"),
                    registry: Registry = Depends(get_registry)):
    return {"chains": registry.c4_routes(slug, from_id, to_id)}


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
