"""Shared access vocabulary and transactional updates."""
from fastapi import HTTPException
from sqlalchemy import update

from .domain import audit, check_version, truss_dict
from .models import Project, Truss

ACCESS_METHODS = ("N", "K", "Ž", "L", "J")


def height_text(project: dict, bay: dict, tr) -> str:
    height = bay.get("height_m")
    if height is None:
        height = project.get("default_height_m")
    value = f'{height:g} m'.replace(".", ",") if height is not None else tr("access.not_set")
    return f'{tr("height.label")}: {value}'


def save_access(db, project, targets, values, technician):
    """CAS each version inside one transaction; a conflict rolls back all items."""
    for truss, expected in targets:
        check_version(truss, expected)
    changed = []
    try:
        for truss, expected in targets:
            old = {field: getattr(truss, field) for field in values}
            if old == values:
                continue
            result = db.execute(update(Truss).where(
                Truss.id == truss.id, Truss.version == expected,
            ).values(**values, version=expected + 1))
            if result.rowcount != 1:
                raise HTTPException(409, "Vazník mezitím změnil jiný technik.")
            audit(db, project_id=project.id, bay_id=truss.bay_id, truss_id=truss.id,
                  technician=technician, action="truss.access.changed", field="access",
                  old=old, new=values, metadata={"bulk": len(targets) > 1})
            changed.append(truss)
        if changed:
            db.execute(update(Project).where(Project.id == project.id).values(revision=Project.revision + 1))
            db.commit()
    except Exception:
        db.rollback()
        raise
    return [truss_dict(truss) for truss in changed]
