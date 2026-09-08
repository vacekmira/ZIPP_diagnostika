import sqlite3
from datetime import datetime, timezone

from alembic import command
from alembic.config import Config

from app.config import get_settings
from scripts.backup import backup_database


def test_alpha1_database_is_backed_up_and_migrated_without_data_changes(tmp_path, monkeypatch):
    database = tmp_path / "alpha1.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    get_settings.cache_clear()
    configuration = Config("alembic.ini")
    command.upgrade(configuration, "0001_initial")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO projects VALUES (1,?,?,?,?,?,?)", ("Alpha 1 hala", "Poznámka", 0, 7, now, now))
        connection.execute("INSERT INTO bays VALUES (1,1,1,?,?,?)", ("Původní loď", now, now))
        connection.execute(
            "INSERT INTO trusses VALUES (1,1,1,?,?,?,?,?,?,?,?,?,?,?)",
            ("V-103A", "normal", 1, 0, 1, "crack", "Původní trhlina", 4, None, now, now),
        )
        connection.execute(
            "INSERT INTO audit_logs VALUES (1,1,1,1,?,?,?,?,?,?,?)",
            ("Novák", "truss.excluded", "excluded", "false", "true", None, now),
        )
        connection.commit()
    backup = backup_database(database, tmp_path / "backups", "preupdate")
    assert backup.is_file() and backup.with_suffix(".json").is_file()

    command.upgrade(configuration, "head")
    with sqlite3.connect(database) as connection:
        project = connection.execute("SELECT name,note,archived,revision,labeling_scheme FROM projects WHERE id=1").fetchone()
        bay = connection.execute("SELECT position,name FROM bays WHERE id=1").fetchone()
        truss = connection.execute(
            "SELECT position,label,type,left_done,right_done,excluded,exclusion_reason,exclusion_note,version FROM trusses WHERE id=1"
        ).fetchone()
        audit = connection.execute("SELECT technician_name,action,field,old_value,new_value FROM audit_logs WHERE id=1").fetchone()
        settings = connection.execute("SELECT auth_version,password_hash FROM app_settings WHERE id=1").fetchone()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert connection.execute('SELECT default_height_m FROM projects').fetchone() == (None,)
        assert connection.execute('SELECT height_m FROM bays').fetchone() == (None,)
        assert connection.execute('SELECT left_access,right_access,access_note FROM trusses').fetchone() == (None, None, None)
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        deletion_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_deletion_logs'"
        ).fetchone()
    assert project == ("Alpha 1 hala", "Poznámka", 0, 7, "legacy")
    assert bay == (1, "Původní loď")
    assert truss == (1, "V-103A", "normal", 1, 0, 1, "crack", "Původní trhlina", 4)
    assert audit == ("Novák", "truss.excluded", "excluded", "false", "true")
    assert settings == (1, None) and revision == "0005_alpha8"
    assert deletion_table == ("project_deletion_logs",)
    get_settings.cache_clear()
