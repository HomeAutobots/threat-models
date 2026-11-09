"""The POST routes. One Registry call each; every rule lives in tmreg."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tmreg.core import Registry, ReviewerSession, StaleRecord

from .api_read import _row
from .registry_dep import get_registry

router = APIRouter(prefix="/api")


class AddBody(BaseModel):
    fields: dict


class EditBody(BaseModel):
    fields: dict
    seen: dict
    reason: str = ""


class DecisionBody(BaseModel):
    note: str
    seen: dict


class MergeBody(BaseModel):
    into: str
    note: str
    seen: dict


class RetireBody(BaseModel):
    reason: str
    seen: dict


class ModelApproveBody(BaseModel):
    note: str
    expected_sha256: str


def human_session(reg: Registry, command: str) -> ReviewerSession:
    """Built per request, never cached: ReviewerSession checks for a terminal itself."""
    return ReviewerSession(reg.config.reviewer_name, reg.config.reviewer_email, command)


def _risk_call(registry: Registry, slug: str, id: str, call):
    try:
        row = call()
    except StaleRecord as e:
        return JSONResponse({"detail": str(e), "current": registry.get_risk(slug, id)},
                            status_code=409)
    return {"risk": row}


@router.post("/{reg}/systems/{slug}/risks")
async def add(slug: str, body: AddBody, registry: Registry = Depends(get_registry)):
    return {"risk": registry.add_risk(slug, body.fields, run_id=None)}


@router.post("/{reg}/systems/{slug}/risks/{id}/edit")
async def edit(slug: str, id: str, body: EditBody, registry: Registry = Depends(get_registry)):
    return _risk_call(registry, slug, id, lambda: registry.edit_risk(
        slug, id, body.fields, run_id=None, seen=body.seen, note=body.reason))


@router.post("/{reg}/systems/{slug}/risks/{id}/approve")
async def approve(slug: str, id: str, body: DecisionBody,
                  registry: Registry = Depends(get_registry)):
    session = human_session(registry, "approve")
    return _risk_call(registry, slug, id, lambda: registry.approve(
        session, slug, id, body.note, seen=body.seen))


@router.post("/{reg}/systems/{slug}/risks/{id}/reject")
async def reject(slug: str, id: str, body: DecisionBody,
                 registry: Registry = Depends(get_registry)):
    session = human_session(registry, "reject")
    return _risk_call(registry, slug, id, lambda: registry.reject(
        session, slug, id, body.note, seen=body.seen))


@router.post("/{reg}/systems/{slug}/risks/{id}/merge")
async def merge(slug: str, id: str, body: MergeBody, registry: Registry = Depends(get_registry)):
    session = human_session(registry, "merge")
    return _risk_call(registry, slug, id, lambda: registry.merge(
        session, slug, id, body.into, body.note, seen=body.seen))


@router.post("/{reg}/systems/{slug}/risks/{id}/retire")
async def retire(slug: str, id: str, body: RetireBody, registry: Registry = Depends(get_registry)):
    session = human_session(registry, "retire")
    return _risk_call(registry, slug, id, lambda: registry.retire(
        session, slug, id, body.reason, seen=body.seen))


@router.post("/{reg}/systems/{slug}/c4/approve")
async def c4_approve(slug: str, body: ModelApproveBody,
                     registry: Registry = Depends(get_registry)):
    session = human_session(registry, "c4 approve")
    try:
        row = registry.c4_approve(session, slug, body.note,
                                  expected_sha256=body.expected_sha256)
    except StaleRecord as e:
        return JSONResponse({"detail": str(e),
                             "current_sha256": registry.c4_status(slug).current_sha256},
                            status_code=409)
    return {"approval": _row(row)}
