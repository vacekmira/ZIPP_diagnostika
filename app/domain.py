from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from .models import AuditLog, Bay, DilationPair, DilationPairMember, Project, ProjectDeletionLog, Truss


TYPE_LABELS = {"normal": "Běžný", "gable": "Štítový", "dilation": "Dilatační"}
REASON_LABELS = {"leak": "Zatečený", "crack": "Trhlina", "other": "Jiné"}


def bay_code(position: int) -> str:
    """Return spreadsheet-style bay code: A..Z, AA..AZ, BA..."""
    if position < 1:
        raise ValueError("Bay position must be positive")
    result = ""
    while position:
        position, remainder = divmod(position - 1, 26)
        result = chr(65 + remainder) + result
    return result


def default_truss_label(labeling_scheme: str, bay_position: int, truss_position: int) -> str:
    """Return a label for a newly inserted truss without touching existing labels.

    ``single_v`` deliberately remains attached to a project if more bays are
    added later: the original first bay keeps using V labels while subsequent
    bays use their physical B/C/... prefixes.
    """
    if labeling_scheme == "single_v" and bay_position == 1:
        return f"V{truss_position}"
    if labeling_scheme in {"single_v", "bay_prefix"}:
        return f"{bay_code(bay_position)}{truss_position}"
    return str(truss_position)


def clean_text(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(422, f"{label} nesmí být prázdný.")
    return value


def require_project(db: Session, project_id: int, *, writable: bool = False) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Zakázka nebyla nalezena.")
    if writable and project.archived:
        raise HTTPException(409, "Archivovanou zakázku je nutné nejprve reaktivovat.")
    return project


def require_bay(db: Session, bay_id: int, *, writable: bool = False) -> Bay:
    bay = db.get(Bay, bay_id)
    if not bay:
        raise HTTPException(404, "Loď nebyla nalezena.")
    require_project(db, bay.project_id, writable=writable)
    return bay


def require_truss(db: Session, truss_id: int, *, writable: bool = False) -> Truss:
    truss = db.scalar(
        select(Truss)
        .where(Truss.id == truss_id)
        .options(selectinload(Truss.pair_membership).selectinload(DilationPairMember.pair))
    )
    if not truss or truss.retired_at is not None:
        raise HTTPException(404, "Vazník nebyl nalezen v aktuální struktuře.")
    require_bay(db, truss.bay_id, writable=writable)
    return truss


def check_version(truss: Truss, expected: int | None) -> None:
    if expected is not None and truss.version != expected:
        raise HTTPException(409, {"message": "Vazník mezitím změnil jiný technik.", "current": truss_dict(truss)})


def bump(project: Project, *trusses: Truss) -> None:
    project.revision += 1
    for truss in trusses:
        truss.version += 1


def audit(
    db: Session,
    *,
    project_id: int,
    technician: str,
    action: str,
    bay_id: int | None = None,
    truss_id: int | None = None,
    field: str | None = None,
    old=None,
    new=None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            project_id=project_id,
            bay_id=bay_id,
            truss_id=truss_id,
            technician_name=clean_text(technician, "Jméno technika"),
            action=action,
            field=field,
            old_value=json.dumps(old, ensure_ascii=False) if old is not None else None,
            new_value=json.dumps(new, ensure_ascii=False) if new is not None else None,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
    )


def create_project(db: Session, *, name: str, note: str | None, bay_count: int, truss_count: int, technician: str) -> Project:
    labeling_scheme = "single_v" if bay_count == 1 else "bay_prefix"
    project = Project(name=clean_text(name, "Název zakázky"), note=(note or "").strip() or None,
                      labeling_scheme=labeling_scheme)
    db.add(project)
    db.flush()
    for bay_position in range(1, bay_count + 1):
        code = bay_code(bay_position)
        bay = Bay(project_id=project.id, position=bay_position, name=f"Loď {code}")
        db.add(bay)
        db.flush()
        db.add_all(
            [
                Truss(
                    bay_id=bay.id,
                    position=position,
                    label=default_truss_label(labeling_scheme, bay_position, position),
                )
                for position in range(1, truss_count + 1)
            ]
        )
    audit(db, project_id=project.id, technician=technician, action="project.created", new={"name": project.name})
    db.commit()
    db.refresh(project)
    return project


def rename_project(db: Session, project: Project, *, name: str, technician: str) -> Project:
    name = clean_text(name, "Název zakázky")
    if project.name == name:
        return project
    old = project.name
    project.name = name
    project.revision += 1
    audit(
        db,
        project_id=project.id,
        technician=technician,
        action="project.name.changed",
        field="name",
        old=old,
        new=name,
    )
    db.commit()
    return project


def permanently_delete_project(
    db: Session,
    project: Project,
    *,
    confirmation_name: str,
    technician: str,
) -> dict:
    """Atomically remove one project graph and retain an FK-free tombstone."""
    if confirmation_name.strip() != project.name:
        raise HTTPException(422, "Potvrzovací název zakázky nesouhlasí.")
    technician = clean_text(technician, "Jméno technika")
    project_id, project_name = project.id, project.name
    bay_ids = list(db.scalars(select(Bay.id).where(Bay.project_id == project_id)))
    truss_ids = list(db.scalars(select(Truss.id).where(Truss.bay_id.in_(bay_ids)))) if bay_ids else []
    pair_ids = list(db.scalars(select(DilationPair.id).where(DilationPair.bay_id.in_(bay_ids)))) if bay_ids else []
    tombstone = ProjectDeletionLog(
        project_id=project_id,
        project_name=project_name,
        technician_name=technician,
        action="project.deleted",
    )
    try:
        db.add(tombstone)
        db.flush()
        db.execute(delete(AuditLog).where(AuditLog.project_id == project_id))
        if pair_ids:
            db.execute(delete(DilationPairMember).where(DilationPairMember.dilation_pair_id.in_(pair_ids)))
            db.execute(delete(DilationPair).where(DilationPair.id.in_(pair_ids)))
        if truss_ids:
            db.execute(delete(DilationPairMember).where(DilationPairMember.truss_id.in_(truss_ids)))
            db.execute(delete(Truss).where(Truss.id.in_(truss_ids)))
        if bay_ids:
            db.execute(delete(Bay).where(Bay.id.in_(bay_ids)))
        db.execute(delete(Project).where(Project.id == project_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "id": project_id,
        "name": project_name,
        "deletion_log_id": tombstone.id,
    }


def progress_for_trusses(trusses: Iterable[Truss]) -> dict:
    completed = required = excluded = 0
    for truss in trusses:
        if truss.retired_at is not None:
            continue
        done = int(truss.left_done) + int(truss.right_done)
        completed += done
        required += done if truss.excluded else 2
        excluded += int(truss.excluded)
    remaining = required - completed
    percent = 100 if required == 0 else round(completed * 100 / required)
    return {"completed": completed, "required": required, "remaining": remaining, "excluded": excluded, "percent": percent}


def duplicate_labels(trusses: Iterable[Truss]) -> set[str]:
    counts: dict[str, int] = {}
    for truss in trusses:
        if truss.retired_at is None:
            key = truss.label.casefold()
            counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count > 1}


def truss_dict(truss: Truss) -> dict:
    membership = truss.pair_membership
    return {
        "id": truss.id,
        "bay_id": truss.bay_id,
        "position": truss.position,
        "label": truss.label,
        "type": truss.type,
        "type_label": TYPE_LABELS[truss.type],
        "left_done": truss.left_done,
        "right_done": truss.right_done,
        "excluded": truss.excluded,
        "exclusion_reason": truss.exclusion_reason,
        "exclusion_reason_label": REASON_LABELS.get(truss.exclusion_reason),
        "exclusion_note": truss.exclusion_note,
        "version": truss.version,
        "pair_id": membership.dilation_pair_id if membership else None,
    }


def bay_dict(bay: Bay) -> dict:
    trusses = [truss for truss in bay.trusses if truss.retired_at is None]
    duplicates = duplicate_labels(trusses)
    return {
        "id": bay.id,
        "project_id": bay.project_id,
        "position": bay.position,
        "name": bay.name,
        "progress": progress_for_trusses(trusses),
        "trusses": [{**truss_dict(t), "duplicate_label": t.label.casefold() in duplicates} for t in trusses],
    }


def project_dict(project: Project) -> dict:
    bays = [bay_dict(bay) for bay in project.bays]
    trusses = [truss for bay in project.bays for truss in bay.trusses]
    return {
        "id": project.id,
        "name": project.name,
        "note": project.note,
        "archived": project.archived,
        "revision": project.revision,
        "progress": progress_for_trusses(trusses),
        "bays": bays,
    }


def set_diagnostic(db: Session, truss: Truss, side: str, done: bool, technician: str, expected: int | None) -> Truss:
    check_version(truss, expected)
    if truss.excluded:
        raise HTTPException(409, "Na vyřazeném vazníku nelze měnit diagnostiku.")
    field = "left_done" if side == "left" else "right_done"
    old = getattr(truss, field)
    if old == done:
        return truss
    project = require_project(db, truss.bay.project_id, writable=True)
    setattr(truss, field, done)
    bump(project, truss)
    audit(db, project_id=project.id, bay_id=truss.bay_id, truss_id=truss.id, technician=technician,
          action=f"diagnostic.{side}.set", field=field, old=old, new=done)
    db.commit()
    return truss


def set_label(db: Session, truss: Truss, label: str, technician: str, expected: int | None) -> Truss:
    check_version(truss, expected)
    label = clean_text(label, "Označení")
    if truss.label == label:
        return truss
    project = require_project(db, truss.bay.project_id, writable=True)
    old = truss.label
    truss.label = label
    bump(project, truss)
    audit(db, project_id=project.id, bay_id=truss.bay_id, truss_id=truss.id, technician=technician,
          action="truss.label.changed", field="label", old=old, new=label, metadata={"position": truss.position})
    db.commit()
    return truss


def set_type(db: Session, truss: Truss, new_type: str, technician: str, expected: int | None) -> Truss:
    check_version(truss, expected)
    if truss.pair_membership:
        raise HTTPException(409, "Vazník je v dilatační dvojici; změňte celou dvojici.")
    if new_type == "dilation":
        raise HTTPException(422, "Dilatační typ lze vytvořit pouze jako dvojici.")
    project = require_project(db, truss.bay.project_id, writable=True)
    old = truss.type
    if old != new_type:
        truss.type = new_type
        bump(project, truss)
        audit(db, project_id=project.id, bay_id=truss.bay_id, truss_id=truss.id, technician=technician,
              action="truss.type.changed", field="type", old=old, new=new_type)
        db.commit()
    return truss


def exclude_truss(db: Session, truss: Truss, reason: str, note: str | None, technician: str, expected: int | None) -> Truss:
    check_version(truss, expected)
    if reason == "other" and not (note or "").strip():
        raise HTTPException(422, "Pro důvod Jiné je poznámka povinná.")
    project = require_project(db, truss.bay.project_id, writable=True)
    old = {"excluded": truss.excluded, "reason": truss.exclusion_reason, "note": truss.exclusion_note}
    truss.excluded = True
    truss.exclusion_reason = reason
    truss.exclusion_note = (note or "").strip() or None
    bump(project, truss)
    audit(db, project_id=project.id, bay_id=truss.bay_id, truss_id=truss.id, technician=technician,
          action="truss.excluded", field="excluded", old=old,
          new={"excluded": True, "reason": reason, "note": truss.exclusion_note})
    db.commit()
    return truss


def restore_truss(db: Session, truss: Truss, technician: str, expected: int | None) -> Truss:
    check_version(truss, expected)
    project = require_project(db, truss.bay.project_id, writable=True)
    old = {"reason": truss.exclusion_reason, "note": truss.exclusion_note}
    truss.excluded = False
    truss.exclusion_reason = None
    truss.exclusion_note = None
    bump(project, truss)
    audit(db, project_id=project.id, bay_id=truss.bay_id, truss_id=truss.id, technician=technician,
          action="truss.restored", field="excluded", old={"excluded": True, **old}, new={"excluded": False})
    db.commit()
    return truss


def create_pair(db: Session, a: Truss, b: Truss, technician: str, version_a: int, version_b: int) -> DilationPair:
    check_version(a, version_a)
    check_version(b, version_b)
    if a.id == b.id or a.bay_id != b.bay_id or abs(a.position - b.position) != 1:
        raise HTTPException(422, "Dilatační dvojici mohou tvořit pouze dva sousední vazníky ve stejné lodi.")
    if a.pair_membership or b.pair_membership:
        raise HTTPException(409, "Jeden z vazníků už je součástí jiné dilatační dvojice.")
    if a.excluded or b.excluded:
        raise HTTPException(409, "Vyřazený vazník nelze zařadit do dilatační dvojice.")
    left, right = sorted((a, b), key=lambda item: item.position)
    project = require_project(db, left.bay.project_id, writable=True)
    pair = DilationPair(bay_id=left.bay_id)
    db.add(pair)
    db.flush()
    db.add_all([
        DilationPairMember(dilation_pair_id=pair.id, truss_id=left.id, member_order=1),
        DilationPairMember(dilation_pair_id=pair.id, truss_id=right.id, member_order=2),
    ])
    old_types = {str(left.id): left.type, str(right.id): right.type}
    left.type = right.type = "dilation"
    bump(project, left, right)
    for truss in (left, right):
        audit(db, project_id=project.id, bay_id=truss.bay_id, truss_id=truss.id, technician=technician,
              action="dilation_pair.created", field="type", old=old_types[str(truss.id)], new="dilation",
              metadata={"pair_id": pair.id, "other_truss_id": right.id if truss.id == left.id else left.id})
    db.commit()
    db.expire(left, ["pair_membership"])
    db.expire(right, ["pair_membership"])
    return pair


def remove_pair(db: Session, pair: DilationPair, technician: str, type_a: str, type_b: str,
                version_a: int, version_b: int) -> list[Truss]:
    members = sorted(pair.members, key=lambda item: item.member_order)
    if len(members) != 2:
        raise HTTPException(500, "Dilatační dvojice má poškozená data.")
    a, b = members[0].truss, members[1].truss
    check_version(a, version_a)
    check_version(b, version_b)
    project = require_project(db, pair.bay.project_id, writable=True)
    pair_id = pair.id
    for truss, new_type in ((a, type_a), (b, type_b)):
        truss.type = new_type
        bump(project, truss)
        audit(db, project_id=project.id, bay_id=truss.bay_id, truss_id=truss.id, technician=technician,
              action="dilation_pair.removed", field="type", old="dilation", new=new_type,
              metadata={"pair_id": pair_id})
    db.delete(pair)
    db.commit()
    db.expire(a, ["pair_membership"])
    db.expire(b, ["pair_membership"])
    return [a, b]


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
