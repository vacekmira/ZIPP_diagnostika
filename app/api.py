from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from . import __version__
from .bay_report import render_bay_report_pdf
from .access import save_access
from .database import get_db
from .export_options import ExportOptions, FontSizeQuery, Orientation, PageSize
from .auth import require_api_auth
from .domain import (
    audit,
    bay_dict,
    bump,
    check_version,
    clean_text,
    create_pair,
    create_project,
    default_truss_label,
    exclude_truss,
    permanently_delete_project,
    project_dict,
    rename_project,
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
from .i18n import normalize_language
from .plan import render_plan_pdf, render_plan_svg
from .plan_pdf import ExportLayoutError
from .realtime import manager
from .schemas import (
    ActorOperation,
    AccessSet,
    AccessNoteSet,
    BulkAccessSet,
    HeightSet,
    BayResize,
    BayUpdate,
    BulkLabelSet,
    DiagnosticSet,
    DilationPairCreate,
    DilationPairRemove,
    ExcludeSet,
    LabelSet,
    ProjectCreate,
    ProjectDelete,
    ProjectNameUpdate,
    TypeSet,
)


router = APIRouter(prefix="/api", dependencies=[Depends(require_api_auth)])


def safe_export_filename(*parts: str, suffix: str = ".pdf") -> str:
    normalized = "_".join(parts)
    normalized = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("._-")
    return f"{(normalized or 'zipp-export')[:180]}{suffix}"


def load_project(db: Session, project_id: int) -> Project:
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .execution_options(populate_existing=True)
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
        .execution_options(populate_existing=True)
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
                             truss_count=payload.default_truss_count, technician=payload.technician_name,
                             default_height_m=payload.default_height_m)
    return project_dict(load_project(db, project.id))


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    return project_dict(load_project(db, project_id))


@router.patch("/projects/{project_id}/name")
async def update_project_name(project_id: int, payload: ProjectNameUpdate, db: Session = Depends(get_db)):
    project = rename_project(
        db,
        require_project(db, project_id, writable=True),
        name=payload.name,
        technician=payload.technician_name,
    )
    event = {
        "type": "project.renamed",
        "project_id": project.id,
        "project_revision": project.revision,
        "project": {"id": project.id, "name": project.name, "revision": project.revision},
    }
    await manager.broadcast(project.id, event)
    # Channel 0 is the existing manager's project-list channel. A page uses
    # either this channel or its project channel, never both in parallel.
    await manager.broadcast(0, event)
    return event["project"]


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, payload: ProjectDelete, db: Session = Depends(get_db)):
    deleted = permanently_delete_project(
        db,
        require_project(db, project_id),
        confirmation_name=payload.confirmation_name,
        technician=payload.technician_name,
    )
    event = {
        "type": "project.deleted",
        "project_id": deleted["id"],
        "project": {"id": deleted["id"], "name": deleted["name"]},
    }
    await manager.broadcast(deleted["id"], event)
    await manager.broadcast(0, event)
    return {**deleted, "deleted": True}


@router.get("/projects/{project_id}/plan.svg")
def project_plan_svg(project_id: int, lang: str = "cs", revision: int | None = None, show_access: bool = False, db: Session = Depends(get_db)):
    project = project_dict(load_project(db, project_id))
    return Response(render_plan_svg(project, normalize_language(lang), show_access=show_access), media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store", "X-Project-Revision": str(project["revision"])})


@router.get("/projects/{project_id}/plan.pdf")
def project_plan_pdf(
    project_id: int,
    lang: str = "cs",
    page_size: PageSize = "A3",
    orientation: Orientation = "landscape",
    font_size: FontSizeQuery = "auto",
    show_access: bool = False,
    db: Session = Depends(get_db),
):
    project = project_dict(load_project(db, project_id))
    try:
        options = ExportOptions(page_size, orientation, font_size, show_access)
        pdf = render_plan_pdf(project, normalize_language(lang), options=options)
    except ExportLayoutError as exc:
        raise HTTPException(422, exc.as_detail()) from exc
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="zipp-plan-project-{project_id}.pdf"',
        "Cache-Control": "no-store",
        "X-Zipp-Page-Size": page_size,
        "X-Zipp-Orientation": orientation,
        "X-Zipp-Font-Size": font_size,
    })


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
    await manager.broadcast(project.id, {"type": "project.reactivated", "project_revision": project.revision})
    return {"id": project.id, "archived": False, "revision": project.revision}


@router.get("/bays/{bay_id}")
def get_bay(bay_id: int, db: Session = Depends(get_db)):
    return bay_dict(load_bay(db, bay_id))


@router.get("/bays/{bay_id}/report.pdf")
def bay_report_pdf(
    bay_id: int,
    lang: str = "cs",
    page_size: PageSize = "A3",
    orientation: Orientation = "landscape",
    font_size: FontSizeQuery = "auto",
    show_access: bool = False,
    db: Session = Depends(get_db),
):
    bay = load_bay(db, bay_id)
    project = project_dict(load_project(db, bay.project_id))
    bay_data = next(item for item in project["bays"] if item["id"] == bay_id)
    created_at = datetime.now().astimezone()
    options = ExportOptions(page_size, orientation, font_size, show_access)
    try:
        pdf = render_bay_report_pdf(
            project, bay_data, normalize_language(lang), created_at, options=options,
        )
    except ExportLayoutError as exc:
        raise HTTPException(422, exc.as_detail()) from exc
    filename = safe_export_filename(project["name"], bay_data["name"], created_at.strftime("%Y-%m-%d"))
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
        "X-Zipp-Page-Size": page_size,
        "X-Zipp-Orientation": orientation,
        "X-Zipp-Font-Size": font_size,
    })


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
                label = default_truss_label(project.labeling_scheme, bay.position, position)
                db.add(Truss(bay_id=bay.id, position=position, label=label))
        project.revision += 1
        audit(db, project_id=project.id, bay_id=bay.id, technician=payload.technician_name,
              action="bay.resized", field="truss_count", old=current, new=payload.truss_count)
        db.commit()
        # The relationship was loaded before new rows were inserted.  Expire it
        # so the response contains the just-created trusses as well.
        db.expire(bay, ["trusses"])
    else:
        affected = [t for t in active if t.position > payload.truss_count]
        impacted = [t for t in affected if t.left_done or t.right_done or t.excluded or t.pair_membership
                    or t.left_access or t.right_access or t.access_note]
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


async def publish_access(db, project, bay_id, changed):
    await manager.broadcast(project.id, {
        "type": "bay.access.updated", "bay_id": bay_id,
        "project_revision": project.revision, "trusses": changed,
    })


@router.put("/trusses/{truss_id}/access/{side}")
async def set_side_access(truss_id: int, side: str, payload: AccessSet, db: Session = Depends(get_db)):
    if side not in {"left", "right"}:
        raise HTTPException(404, "Neznámá strana.")
    truss = require_truss(db, truss_id, writable=True)
    project = require_project(db, truss.bay.project_id, writable=True)
    changed = save_access(db, project, [(truss, payload.expected_version)],
                          {f"{side}_access": payload.method}, payload.technician_name)
    await publish_access(db, project, truss.bay_id, changed)
    return truss_dict(truss)


@router.put("/trusses/{truss_id}/access-note")
async def set_access_note(truss_id: int, payload: AccessNoteSet, db: Session = Depends(get_db)):
    truss = require_truss(db, truss_id, writable=True)
    project = require_project(db, truss.bay.project_id, writable=True)
    changed = save_access(db, project, [(truss, payload.expected_version)],
                          {"access_note": (payload.note or "").strip() or None}, payload.technician_name)
    await publish_access(db, project, truss.bay_id, changed)
    return truss_dict(truss)


@router.post("/bays/{bay_id}/access/bulk")
async def bulk_access(bay_id: int, payload: BulkAccessSet, db: Session = Depends(get_db)):
    bay = require_bay(db, bay_id, writable=True)
    project = require_project(db, bay.project_id, writable=True)
    targets = []
    for item in payload.items:
        truss = require_truss(db, item.truss_id, writable=True)
        if truss.bay_id != bay.id:
            raise HTTPException(422, "Vazník nepatří do této lodě.")
        targets.append((truss, item.expected_version))
    values = payload.model_dump(include={"left_access", "right_access"}, exclude_unset=True)
    changed = save_access(db, project, targets, values, payload.technician_name)
    await publish_access(db, project, bay.id, changed)
    return {"changed": changed, "project_revision": project.revision}


async def save_height(db, project, target, field, payload):
    old = getattr(target, field)
    result = db.execute(update(Project).where(
        Project.id == project.id, Project.revision == payload.expected_revision,
    ).values(revision=Project.revision + 1))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Zakázku mezitím změnil jiný technik. Obnovte stránku.")
    setattr(target, field, payload.height_m)
    audit(db, project_id=project.id, bay_id=target.id if isinstance(target, Bay) else None,
          technician=payload.technician_name, action="height.changed", field=field,
          old=old, new=payload.height_m)
    db.commit()
    data = project_dict(load_project(db, project.id))
    await manager.broadcast(project.id, {"type": "height.updated", "project": data,
                                        "project_revision": project.revision})
    return data


@router.put("/projects/{project_id}/height")
async def project_height(project_id: int, payload: HeightSet, db: Session = Depends(get_db)):
    project = require_project(db, project_id, writable=True)
    return await save_height(db, project, project, "default_height_m", payload)


@router.put("/bays/{bay_id}/height")
async def bay_height(bay_id: int, payload: HeightSet, db: Session = Depends(get_db)):
    bay = require_bay(db, bay_id, writable=True)
    project = require_project(db, bay.project_id, writable=True)
    return await save_height(db, project, bay, "height_m", payload)


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
    project = db.get(Project, a.bay.project_id)
    await manager.broadcast(project.id, {"type": "dilation_pair.created", "bay_id": bay_id,
                                         "pair_id": pair.id, "project_revision": project.revision})
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
    project = db.get(Project, pair.bay.project_id)
    await manager.broadcast(project.id, {"type": "dilation_pair.removed", "bay_id": pair.bay_id,
                                         "project_revision": project.revision})
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
