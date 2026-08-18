from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import __version__
from .database import get_db
from .domain import (
    audit,
    bay_dict,
    bump,
    check_version,
    clean_text,
    create_pair,
    create_project,
    exclude_truss,
    project_dict,
    remove_pair,
    require_bay,
    require_project,
    require_truss,
    restore_truss,
    set_diagnostic,
    set_label,
    set_type,
    truss_dict,
    utc_iso,
)
from .models import AuditLog, Bay, DilationPair, DilationPairMember, Project, Truss
from .realtime import manager
from .schemas import (
    ActorOperation,
    BayResize,
    BayUpdate,
    BulkLabelSet,
    DiagnosticSet,
    DilationPairCreate,
    DilationPairRemove,
    ExcludeSet,
    LabelSet,
    ProjectCreate,
    TypeSet,
)


router = APIRouter(prefix="/api")


def load_project(db: Session, project_id: int) -> Project:
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.bays)
            .selectinload(Bay.trusses)
            .selectinload(Truss.pair_membership)
        )
    )
    if not project:
        raise HTTPException(404, "Zakázka nebyla nalezena.")
    return project


def load_bay(db: Session, bay_id: int) -> Bay:
    bay = db.scalar(
        select(Bay)
        .where(Bay.id == bay_id)
        .options(selectinload(Bay.trusses).selectinload(Truss.pair_membership))
    )
    if not bay:
        raise HTTPException(404, "Loď nebyla nalezena.")
    return bay


async def publish_truss(db: Session, truss: Truss, event_type: str = "truss.updated") -> None:
    project = db.get(Project, truss.bay.project_id)
    await manager.broadcast(project.id, {
        "type": event_type,
        "project_id": project.id,
        "bay_id": truss.bay_id,
        "project_revision": project.revision,
        "truss": truss_dict(truss),
    })


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    projects = db.scalars(
        select(Project).options(selectinload(Project.bays).selectinload(Bay.trusses).selectinload(Truss.pair_membership))
        .order_by(Project.archived, Project.updated_at.desc())
    ).all()
    return [project_dict(project) for project in projects]


@router.post("/projects", status_code=201)
async def add_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = create_project(db, name=payload.name, note=payload.note, bay_count=payload.bay_count,
                             truss_count=payload.default_truss_count, technician=payload.technician_name)
    return project_dict(load_project(db, project.id))


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    return project_dict(load_project(db, project_id))


@router.post("/projects/{project_id}/archive")
async def archive_project(project_id: int, payload: ActorOperation, db: Session = Depends(get_db)):
    project = require_project(db, project_id, writable=True)
    project.archived = True
    project.revision += 1
    audit(db, project_id=project.id, technician=payload.technician_name, action="project.archived",
          field="archived", old=False, new=True)
    db.commit()
    await manager.broadcast(project.id, {"type": "project.archived", "project_revision": project.revision})
    return {"id": project.id, "archived": True, "revision": project.revision}


@router.post("/projects/{project_id}/reactivate")
async def reactivate_project(project_id: int, payload: ActorOperation, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    if not project.archived:
        return {"id": project.id, "archived": False, "revision": project.revision}
    project.archived = False
    project.revision += 1
    audit(db, project_id=project.id, technician=payload.technician_name, action="project.reactivated",
          field="archived", old=True, new=False)
    db.commit()
    return {"id": project.id, "archived": False, "revision": project.revision}


@router.get("/bays/{bay_id}")
def get_bay(bay_id: int, db: Session = Depends(get_db)):
    return bay_dict(load_bay(db, bay_id))


@router.patch("/bays/{bay_id}")
async def update_bay(bay_id: int, payload: BayUpdate, db: Session = Depends(get_db)):
    bay = require_bay(db, bay_id, writable=True)
    old = bay.name
    bay.name = clean_text(payload.name, "Název lodě")
    project = require_project(db, bay.project_id, writable=True)
    project.revision += 1
    audit(db, project_id=project.id, bay_id=bay.id, technician=payload.technician_name,
          action="bay.name.changed", field="name", old=old, new=bay.name)
    db.commit()
    await manager.broadcast(project.id, {"type": "bay.updated", "bay_id": bay.id, "project_revision": project.revision})
    return {"id": bay.id, "name": bay.name, "project_revision": project.revision}


@router.post("/bays/{bay_id}/resize")
async def resize_bay(bay_id: int, payload: BayResize, db: Session = Depends(get_db)):
    bay = load_bay(db, bay_id)
    project = require_project(db, bay.project_id, writable=True)
    active = sorted((t for t in bay.trusses if t.retired_at is None), key=lambda t: t.position)
    current = len(active)
    if payload.truss_count == current:
        return bay_dict(bay)
    if payload.truss_count > current:
        by_position = {t.position: t for t in bay.trusses}
        for position in range(current + 1, payload.truss_count + 1):
            if position in by_position:
                by_position[position].retired_at = None
                by_position[position].version += 1
            else:
                db.add(Truss(bay_id=bay.id, position=position, label=str(position)))
        project.revision += 1
        audit(db, project_id=project.id, bay_id=bay.id, technician=payload.technician_name,
              action="bay.resized", field="truss_count", old=current, new=payload.truss_count)
        db.commit()
    else:
        affected = [t for t in active if t.position > payload.truss_count]
        impacted = [t for t in affected if t.left_done or t.right_done or t.excluded or t.pair_membership]
        if impacted and not payload.confirm:
            raise HTTPException(409, {"message": "Zmenšení skryje vazníky s existujícími daty.",
                                      "affected": [truss_dict(t) for t in affected], "confirmation_required": True})
        affected_ids = {t.id for t in affected}
        for truss in affected:
            if truss.pair_membership:
                pair = truss.pair_membership.pair
                member_ids = {member.truss_id for member in pair.members}
                if not member_ids.issubset(affected_ids):
                    raise HTTPException(422, "Zmenšení by rozdělilo dilatační dvojici.")
        handled_pairs: set[int] = set()
        for truss in affected:
            if truss.pair_membership and truss.pair_membership.dilation_pair_id not in handled_pairs:
                pair = truss.pair_membership.pair
                handled_pairs.add(pair.id)
                for member in pair.members:
                    member.truss.type = "normal"
                db.delete(pair)
            truss.retired_at = datetime.now(timezone.utc)
            truss.version += 1
        project.revision += 1
        audit(db, project_id=project.id, bay_id=bay.id, technician=payload.technician_name,
              action="bay.resized", field="truss_count", old=current, new=payload.truss_count,
              metadata={"retired_truss_ids": sorted(affected_ids)})
        db.commit()
    await manager.broadcast(project.id, {"type": "bay.resized", "bay_id": bay.id, "project_revision": project.revision})
    return bay_dict(load_bay(db, bay.id))


@router.put("/trusses/{truss_id}/diagnostics/{side}")
async def diagnostic(truss_id: int, side: str, payload: DiagnosticSet, db: Session = Depends(get_db)):
    if side not in {"left", "right"}:
        raise HTTPException(404, "Neznámá strana.")
    truss = set_diagnostic(db, require_truss(db, truss_id, writable=True), side, payload.done,
                           payload.technician_name, payload.expected_version)
    await publish_truss(db, truss)
    return truss_dict(truss)


@router.patch("/trusses/{truss_id}/label")
async def change_label(truss_id: int, payload: LabelSet, db: Session = Depends(get_db)):
    truss = set_label(db, require_truss(db, truss_id, writable=True), payload.label,
                      payload.technician_name, payload.expected_version)
    await publish_truss(db, truss)
    return truss_dict(truss)


@router.post("/bays/{bay_id}/labels/bulk")
async def bulk_labels(bay_id: int, payload: BulkLabelSet, db: Session = Depends(get_db)):
    bay = require_bay(db, bay_id, writable=True)
    by_id = {t.id: t for t in db.scalars(select(Truss).where(Truss.bay_id == bay.id, Truss.retired_at.is_(None))).all()}
    changed: list[Truss] = []
    project = require_project(db, bay.project_id, writable=True)
    for item in payload.items:
        truss = by_id.get(item.truss_id)
        if not truss:
            raise HTTPException(422, "Vazník nepatří do této lodě.")
        check_version(truss, item.expected_version)
        label = clean_text(item.label, "Označení")
        if truss.label != label:
            old = truss.label
            truss.label = label
            truss.version += 1
            changed.append(truss)
            audit(db, project_id=project.id, bay_id=bay.id, truss_id=truss.id, technician=payload.technician_name,
                  action="truss.label.changed", field="label", old=old, new=label,
                  metadata={"position": truss.position, "bulk": True})
    if changed:
        project.revision += 1
        db.commit()
        await manager.broadcast(project.id, {"type": "bay.labels.updated", "bay_id": bay.id,
                                             "project_revision": project.revision})
    return {"changed": [truss_dict(t) for t in changed], "project_revision": project.revision}


@router.patch("/trusses/{truss_id}/type")
async def change_type(truss_id: int, payload: TypeSet, db: Session = Depends(get_db)):
    truss = set_type(db, require_truss(db, truss_id, writable=True), payload.type,
                     payload.technician_name, payload.expected_version)
    await publish_truss(db, truss)
    return truss_dict(truss)


@router.post("/trusses/{truss_id}/exclude")
async def exclude(truss_id: int, payload: ExcludeSet, db: Session = Depends(get_db)):
    truss = exclude_truss(db, require_truss(db, truss_id, writable=True), payload.reason, payload.note,
                          payload.technician_name, payload.expected_version)
    await publish_truss(db, truss, "truss.excluded")
    return truss_dict(truss)


@router.post("/trusses/{truss_id}/restore")
async def restore(truss_id: int, payload: ActorOperation, db: Session = Depends(get_db)):
    truss = restore_truss(db, require_truss(db, truss_id, writable=True), payload.technician_name,
                          payload.expected_version)
    await publish_truss(db, truss, "truss.restored")
    return truss_dict(truss)


@router.post("/bays/{bay_id}/dilation-pairs", status_code=201)
async def add_pair(bay_id: int, payload: DilationPairCreate, db: Session = Depends(get_db)):
    a, b = require_truss(db, payload.truss_a_id, writable=True), require_truss(db, payload.truss_b_id, writable=True)
    if a.bay_id != bay_id or b.bay_id != bay_id:
        raise HTTPException(422, "Oba vazníky musí patřit do zvolené lodě.")
    pair = create_pair(db, a, b, payload.technician_name, payload.expected_version_a, payload.expected_version_b)
    await manager.broadcast(a.bay.project_id, {"type": "dilation_pair.created", "bay_id": bay_id, "pair_id": pair.id})
    return {"id": pair.id, "members": [truss_dict(a), truss_dict(b)]}


@router.post("/dilation-pairs/{pair_id}/remove")
async def delete_pair(pair_id: int, payload: DilationPairRemove, db: Session = Depends(get_db)):
    pair = db.scalar(select(DilationPair).where(DilationPair.id == pair_id).options(
        selectinload(DilationPair.bay),
        selectinload(DilationPair.members).selectinload(DilationPairMember.truss),
    ))
    if not pair:
        raise HTTPException(404, "Dilatační dvojice nebyla nalezena.")
    trusses = remove_pair(db, pair, payload.technician_name, payload.type_a, payload.type_b,
                          payload.expected_version_a, payload.expected_version_b)
    await manager.broadcast(pair.bay.project_id, {"type": "dilation_pair.removed", "bay_id": pair.bay_id})
    return {"removed": pair_id, "members": [truss_dict(t) for t in trusses]}


@router.get("/projects/{project_id}/audit")
def project_audit(project_id: int, limit: int = 100, db: Session = Depends(get_db)):
    require_project(db, project_id)
    logs = db.scalars(select(AuditLog).where(AuditLog.project_id == project_id)
                      .order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 500))).all()
    return [{"id": log.id, "bay_id": log.bay_id, "truss_id": log.truss_id,
             "technician_name": log.technician_name, "action": log.action, "field": log.field,
             "old_value": log.old_value, "new_value": log.new_value, "metadata": log.metadata_json,
             "created_at": utc_iso(log.created_at)} for log in logs]
