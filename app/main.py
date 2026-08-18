from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from . import __version__
from .api import load_bay, load_project, router as api_router
from .database import engine, get_db
from .domain import REASON_LABELS, TYPE_LABELS, bay_dict, project_dict, truss_dict, utc_iso
from .models import AuditLog, Bay, DilationPairMember, Project, Truss
from .realtime import manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="ZIPP Diagnostika", version=__version__, lifespan=lifespan)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update(version=__version__, type_labels=TYPE_LABELS, reason_labels=REASON_LABELS)


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok", "version": __version__}
    except Exception:
        raise HTTPException(503, {"status": "error", "database": "unavailable", "version": __version__})


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db=Depends(get_db)):
    projects = db.scalars(select(Project).options(
        selectinload(Project.bays).selectinload(Bay.trusses).selectinload(Truss.pair_membership)
    ).order_by(Project.updated_at.desc())).all()
    serialized = [project_dict(project) for project in projects]
    return templates.TemplateResponse(request, "index.html", {
        "projects": [p for p in serialized if not p["archived"]],
        "archived": [p for p in serialized if p["archived"]],
    })


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_page(request: Request, project_id: int, db=Depends(get_db)):
    project = project_dict(load_project(db, project_id))
    return templates.TemplateResponse(request, "project.html", {"project": project})


@app.get("/bays/{bay_id}", response_class=HTMLResponse)
def bay_page(request: Request, bay_id: int, db=Depends(get_db)):
    bay = load_bay(db, bay_id)
    project = db.get(Project, bay.project_id)
    data = bay_dict(bay)
    pairs: dict[int, list[int]] = {}
    for truss in data["trusses"]:
        if truss["pair_id"]:
            pairs.setdefault(truss["pair_id"], []).append(truss["id"])
    return templates.TemplateResponse(request, "bay.html", {
        "bay": data, "project": {"id": project.id, "name": project.name, "archived": project.archived}, "pairs": pairs
    })


@app.get("/bays/{bay_id}/settings", response_class=HTMLResponse)
def bay_settings(request: Request, bay_id: int, db=Depends(get_db)):
    bay = load_bay(db, bay_id)
    project = db.get(Project, bay.project_id)
    data = bay_dict(bay)
    return templates.TemplateResponse(request, "bay_settings.html", {
        "bay": data, "project": {"id": project.id, "name": project.name, "archived": project.archived}
    })


@app.get("/trusses/{truss_id}", response_class=HTMLResponse)
def truss_page(request: Request, truss_id: int, db=Depends(get_db)):
    truss = db.scalar(select(Truss).where(Truss.id == truss_id).options(
        selectinload(Truss.bay),
        selectinload(Truss.pair_membership).selectinload(DilationPairMember.pair),
    ))
    if not truss:
        raise HTTPException(404, "Vazník nebyl nalezen.")
    logs = db.scalars(select(AuditLog).where(AuditLog.truss_id == truss.id)
                      .order_by(AuditLog.id.desc()).limit(100)).all()
    data = truss_dict(truss)
    bay = {"id": truss.bay.id, "name": truss.bay.name, "project_id": truss.bay.project_id}
    audit = [{"technician": log.technician_name, "action": log.action, "field": log.field,
              "old": log.old_value, "new": log.new_value, "created_at": utc_iso(log.created_at)} for log in logs]
    return templates.TemplateResponse(request, "truss.html", {
        "truss": data, "bay": bay, "audit": audit, "project": {"id": bay["project_id"]}
    })


@app.websocket("/ws/projects/{project_id}")
async def project_websocket(websocket: WebSocket, project_id: int):
    await manager.connect(project_id, websocket)
    await websocket.send_json({"type": "connected", "project_id": project_id})
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
    except Exception:
        manager.disconnect(project_id, websocket)
