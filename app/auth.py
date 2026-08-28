from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import AppSettings


logger = logging.getLogger("zipp.auth")
password_hasher = PasswordHasher()
MIN_PASSWORD_LENGTH = 10


def get_app_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1, auth_version=1)
        db.add(settings)
        db.flush()
    return settings


def is_authenticated(session: dict, db: Session) -> bool:
    settings = get_app_settings(db)
    return bool(settings.password_hash and session.get("authenticated") is True
                and session.get("auth_version") == settings.auth_version)


def require_api_auth(request: Request, db: Session = Depends(get_db)) -> None:
    if not is_authenticated(request.session, db):
        raise HTTPException(401, "authentication_required")


def require_page_auth(request: Request, db: Session = Depends(get_db)) -> None:
    if not is_authenticated(request.session, db):
        target = quote(str(request.url.path), safe="/")
        raise HTTPException(303, headers={"Location": f"/login?next={target}"})


def set_password(db: Session, password: str) -> AppSettings:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Heslo musí mít alespoň {MIN_PASSWORD_LENGTH} znaků.")
    settings = get_app_settings(db)
    settings.password_hash = password_hasher.hash(password)
    settings.auth_version += 1
    settings.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    return settings


def verify_password(db: Session, password: str) -> AppSettings | None:
    settings = get_app_settings(db)
    if not settings.password_hash:
        return None
    try:
        if password_hasher.verify(settings.password_hash, password):
            if password_hasher.check_needs_rehash(settings.password_hash):
                settings.password_hash = password_hasher.hash(password)
                db.commit()
            return settings
    except (VerifyMismatchError, InvalidHashError):
        return None
    return None


class LoginRateLimiter:
    def __init__(self) -> None:
        self.attempts: dict[str, deque[float]] = defaultdict(deque)
        self.global_attempts: deque[float] = deque()

    def _trim(self, queue: deque[float], now: float, window: int = 60) -> None:
        while queue and queue[0] < now - window:
            queue.popleft()

    async def check(self, client_key: str) -> bool:
        now = time.monotonic()
        local = self.attempts[client_key]
        self._trim(local, now)
        self._trim(self.global_attempts, now)
        if len(local) >= 8 or len(self.global_attempts) >= 80:
            await asyncio.sleep(2)
            return False
        return True

    async def failed(self, client_key: str) -> None:
        now = time.monotonic()
        self.attempts[client_key].append(now)
        self.global_attempts.append(now)
        count = len(self.attempts[client_key])
        if count >= 3:
            await asyncio.sleep(min(0.5 * (count - 2), 3.0))

    def succeeded(self, client_key: str) -> None:
        self.attempts.pop(client_key, None)


login_limiter = LoginRateLimiter()
