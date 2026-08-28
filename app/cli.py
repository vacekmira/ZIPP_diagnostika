from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from .auth import MIN_PASSWORD_LENGTH, get_app_settings, set_password
from .database import SessionLocal, engine


def prompt_password() -> str:
    first = getpass.getpass(f"Nové společné heslo (min. {MIN_PASSWORD_LENGTH} znaků): ")
    second = getpass.getpass("Potvrzení hesla: ")
    if first != second:
        raise ValueError("Hesla se neshodují.")
    return first


def change_password(*, only_if_missing: bool = False) -> int:
    with SessionLocal() as db:
        current = get_app_settings(db)
        if only_if_missing and current.password_hash:
            print("Společné heslo už je nastavené.")
            return 0
        try:
            settings = set_password(db, prompt_password())
        except (ValueError, EOFError, KeyboardInterrupt) as exc:
            print(f"CHYBA: {exc}", file=sys.stderr)
            return 1
        print(f"Heslo bylo bezpečně uloženo. Všechny staré session byly zneplatněny (verze {settings.auth_version}).")
        return 0


def check_schema() -> int:
    configuration = Config("alembic.ini")
    expected = ScriptDirectory.from_config(configuration).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != expected:
        print(f"CHYBA: Databáze vyžaduje migraci (aktuální {current or 'žádná'}, očekávaná {expected}).", file=sys.stderr)
        return 2
    print(f"Databázové schéma je aktuální ({current}).")
    return 0


def ensure_session_secret(env_path: Path) -> int:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    generated = secrets.token_urlsafe(48)
    found = False
    changed = False
    result: list[str] = []
    for line in lines:
        if line.startswith("SESSION_SECRET="):
            found = True
            if not line.partition("=")[2].strip():
                line = f"SESSION_SECRET={generated}"
                changed = True
        result.append(line)
    if not found:
        result.append(f"SESSION_SECRET={generated}")
        changed = True
    if changed:
        env_path.write_text("\n".join(result) + "\n", encoding="utf-8")
        print(f"Session secret byl bezpečně vytvořen v {env_path}.")
    else:
        print(f"Session secret v {env_path} už je nastavený.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Lokální administrace ZIPP Diagnostiky")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("change-password", help="Nastaví nové společné heslo a odhlásí všechny klienty")
    commands.add_parser("ensure-password", help="Vyžádá heslo jen pokud ještě není nastavené")
    commands.add_parser("check-schema", help="Ověří, že jsou provedené všechny migrace")
    secret_parser = commands.add_parser("ensure-session-secret", help="Doplní náhodný session secret do env souboru")
    secret_parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()
    if args.command == "check-schema":
        return check_schema()
    if args.command == "ensure-session-secret":
        return ensure_session_secret(args.env)
    return change_password(only_if_missing=args.command == "ensure-password")


if __name__ == "__main__":
    raise SystemExit(main())
