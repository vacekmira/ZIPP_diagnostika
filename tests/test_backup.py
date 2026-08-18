import sqlite3

from scripts.backup import backup_database


def test_backup_uses_sqlite_backup_and_is_readable(tmp_path):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('diagnostika')")
    result = backup_database(source, tmp_path / "backups", retention=2)
    assert result.is_file()
    assert result.with_suffix(".json").is_file()
    with sqlite3.connect(result) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "diagnostika"
