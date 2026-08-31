import asyncio
from contextlib import asynccontextmanager

import logging
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from . import __version__
from .api import load_bay, load_project, router as api_router
from .auth import get_app_settings, is_authenticated, login_limiter, require_page_auth, verify_password
from .config import get_settings
from .database import SessionLocal, engine, get_db
from .domain import REASON_LABELS, TYPE_LABELS, bay_dict, project_dict, truss_dict, utc_iso
from .i18n import catalog_json, request_language, translator
from .models import AuditLog, Bay, DilationPairMember, Project, Truss
from .realtime import manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.session_secret == "development-only-change-me":
        if settings.public_url:
            raise RuntimeError("Pro veřejný provoz nejprve nastavte náhodný SESSION_SECRET.")
        logger.warning("Používá se pouze vývojový session secret; před nasazením spusťte ensure-session-secret.")
    if settings.public_url.lower().startswith("https://") and not settings.session_cookie_secure:
        raise RuntimeError("Pro HTTPS nastavte SESSION_COOKIE_SECURE=true.")
    yield


app = FastAPI(
    title="ZIPP Diagnostika", version=__version__, lifespan=lifespan,
    docs_url=None, redoc_url=None, openapi_url=None,
)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="zipp_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.session_cookie_secure,
)
app.state.session_factory = SessionLocal
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update(
    version=__version__,
    asset_version=__version__.lower().replace(" ", "-"),
    type_labels=TYPE_LABELS,
    reason_labels=REASON_LABELS,
)
logger = logging.getLogger("uvicorn.error")


def template_context(request: Request, **values) -> dict:
    language = request_language(request)
    return {"lang": language, "tr": translator(language), "i18n_json": catalog_json(), **values}


def safe_next(value: str | None) -> str:
    if not value:
        return "/"
    parsed = urlparse(value)
    return value if not parsed.scheme and not parsed.netloc and value.startswith("/") else "/"


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok", "version": __version__}
    except Exception:
        raise HTTPException(503, {"status": "error", "database": "unavailable", "version": __version__})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", db=Depends(get_db)):
    if is_authenticated(request.session, db):
        return RedirectResponse(safe_next(next), status_code=303)
    configured = bool(get_app_settings(db).password_hash)
    return templates.TemplateResponse(request, "login.html", template_context(
        request, configured=configured, error=None, next=safe_next(next)
    ))


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form(...), next: str = Form("/"), db=Depends(get_db)):
    language = request_language(request)
    tr = translator(language)
    configured = bool(get_app_settings(db).password_hash)
    client_key = request.headers.get("CF-Connecting-IP") or (request.client.host if request.client else "unknown")
    if not await login_limiter.check(client_key):
        return templates.TemplateResponse(request, "login.html", template_context(
            request, configured=configured, error=tr("login.rate_limited"), next=safe_next(next)
        ), status_code=429)
    matched = await run_in_threadpool(verify_password, db, password)
    if matched is None:
        await login_limiter.failed(client_key)
        error = tr("login.not_configured") if not configured else tr("login.bad")
        return templates.TemplateResponse(request, "login.html", template_context(
            request, configured=configured, error=error, next=safe_next(next)
        ), status_code=401)
    login_limiter.succeeded(client_key)
    request.session.clear()
    request.session.update({"authenticated": True, "auth_version": matched.auth_version})
    return RedirectResponse(safe_next(next), status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db=Depends(get_db), _auth=Depends(require_page_auth)):
    projects = db.scalars(select(Project).options(
        selectinload(Project.bays).selectinload(Bay.trusses).selectinload(Truss.pair_membership)
    ).order_by(Project.updated_at.desc())).all()
    serialized = [project_dict(project) for project in projects]
    return templates.TemplateResponse(request, "index.html", template_context(
        request,
        projects=[p for p in serialized if not p["archived"]],
        archived=[p for p in serialized if p["archived"]],
    ))


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_page(request: Request, project_id: int, db=Depends(get_db), _auth=Depends(require_page_auth)):
    project = project_dict(load_project(db, project_id))
    return templates.TemplateResponse(request, "project.html", template_context(request, project=project))


@app.get("/projects/{project_id}/plan", response_class=HTMLResponse)
def project_plan_page(request: Request, project_id: int, db=Depends(get_db), _auth=Depends(require_page_auth)):
    project = project_dict(load_project(db, project_id))
    return templates.TemplateResponse(request, "plan.html", template_context(request, project=project))


@app.get("/bays/{bay_id}", response_class=HTMLResponse)
def bay_page(request: Request, bay_id: int, db=Depends(get_db), _auth=Depends(require_page_auth)):
    bay = load_bay(db, bay_id)
    project = db.get(Project, bay.project_id)
    data = bay_dict(bay)
    pairs: dict[int, list[int]] = {}
    for truss in data["trusses"]:
        if truss["pair_id"]:
            pairs.setdefault(truss["pair_id"], []).append(truss["id"])
    return templates.TemplateResponse(request, "bay.html", template_context(
        request, bay=data, project={"id": project.id, "name": project.name, "archived": project.archived}, pairs=pairs
    ))


@app.get("/bays/{bay_id}/settings", response_class=HTMLResponse)
def bay_settings(request: Request, bay_id: int, db=Depends(get_db), _auth=Depends(require_page_auth)):
    bay = load_bay(db, bay_id)
    project = db.get(Project, bay.project_id)
    data = bay_dict(bay)
    return templates.TemplateResponse(request, "bay_settings.html", template_context(
        request, bay=data, project={"id": project.id, "name": project.name, "archived": project.archived}
    ))


@app.get("/trusses/{truss_id}", response_class=HTMLResponse)
def truss_page(request: Request, truss_id: int, db=Depends(get_db), _auth=Depends(require_page_auth)):
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
    tr = translator(request_language(request))
    audit = [{"technician": log.technician_name, "action": tr(f"audit.action.{log.action}"),
              "field": tr(f"audit.field.{log.field}") if log.field else None,
              "old": log.old_value, "new": log.new_value, "created_at": utc_iso(log.created_at)} for log in logs]
    return templates.TemplateResponse(request, "truss.html", template_context(
        request, truss=data, bay=bay, audit=audit, project={"id": bay["project_id"]}
    ))


async def _run_realtime_websocket(websocket: WebSocket, channel: int, connected_message: dict):
    factory = getattr(websocket.app.state, "session_factory", SessionLocal)
    connection = None
    close_code = None
    close_reason = ""
    try:
        connection = await manager.connect(channel, websocket)
        await manager.send_json(connection, {
            "type": "connected", "connection_id": connection.id, **connected_message,
        })
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                message = None
            with factory() as db:
                if not is_authenticated(websocket.scope.get("session", {}), db):
                    await websocket.close(code=4401, reason="session_invalidated")
                    close_code, close_reason = 4401, "session_invalidated"
                    return
            if message == "ping":
                await manager.send_text(connection, "pong")
    except WebSocketDisconnect as exc:
        close_code = exc.code
        close_reason = getattr(exc, "reason", "") or "client_disconnect"
    except Exception as exc:
        close_reason = type(exc).__name__
        logger.exception("Unexpected WebSocket error channel=%s connection=%s", channel,
                         connection.id if connection else "unaccepted")
    finally:
        if connection:
            manager.disconnect(channel, connection.id, code=close_code, reason=close_reason)


@app.websocket("/ws/projects")
async def project_list_websocket(websocket: WebSocket):
    factory = getattr(websocket.app.state, "session_factory", SessionLocal)
    with factory() as db:
        if not is_authenticated(websocket.scope.get("session", {}), db):
            logger.warning("WebSocket authentication rejected channel=project-list")
            await websocket.close(code=4401, reason="authentication_required")
            return
    await _run_realtime_websocket(websocket, 0, {"channel": "project-list"})


@app.websocket("/ws/projects/{project_id}")
async def project_websocket(websocket: WebSocket, project_id: int):
    factory = getattr(websocket.app.state, "session_factory", SessionLocal)
    with factory() as db:
        session = websocket.scope.get("session", {})
        if not is_authenticated(session, db):
            logger.warning("WebSocket authentication rejected project=%s", project_id)
            await websocket.close(code=4401, reason="authentication_required")
            return
        if db.get(Project, project_id) is None:
            await websocket.close(code=4404, reason="project_not_found")
            return
    await _run_realtime_websocket(websocket, project_id, {"project_id": project_id})
