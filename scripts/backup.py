from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path


def backup_database(source: Path, destination_dir: Path, prefix: str = "manual", retention: int = 30) -> Path:
    if not source.is_file():
        raise FileNotFoundError(f"Databáze neexistuje: {source}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    final_path = destination_dir / f"{prefix}_{stamp}.sqlite3"
    temp_path = final_path.with_suffix(".tmp")
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(temp_path)) as dst:
        src.backup(dst)
        dst.commit()
    with closing(sqlite3.connect(temp_path)) as check:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            temp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Kontrola zálohy selhala: {result}")
    temp_path.replace(final_path)
    digest = hashlib.sha256(final_path.read_bytes()).hexdigest()
    final_path.with_suffix(".json").write_text(json.dumps({"source": str(source), "created_at": datetime.now().isoformat(),
                                                           "sha256": digest}, ensure_ascii=False, indent=2), encoding="utf-8")
    backups = sorted(destination_dir.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[max(retention, 1):]:
        old.unlink(missing_ok=True)
        old.with_suffix(".json").unlink(missing_ok=True)
    return final_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Bezpečná SQLite záloha ZIPP Diagnostics")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--prefix", default="manual")
    parser.add_argument("--retention", type=int, default=30)
    args = parser.parse_args()
    try:
        if args.database is None or args.destination is None:
            from app.config import get_settings
            settings = get_settings()
            args.database = args.database or settings.database_path
            args.destination = args.destination or settings.backup_path
            if args.retention == 30:
                args.retention = settings.backup_retention
        path = backup_database(args.database, args.destination, args.prefix, args.retention)
        print(f"Záloha vytvořena a ověřena: {path}")
        return 0
    except Exception as exc:
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
