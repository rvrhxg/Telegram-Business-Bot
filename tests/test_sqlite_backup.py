import sqlite3
import pytest
from app.sqlite_backup import snapshot


def test_wal_snapshot_restore_foreign_keys_and_no_overwrite(tmp_path):
    source=tmp_path/'source.sqlite'
    with sqlite3.connect(source) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(id INTEGER REFERENCES parent(id)); INSERT INTO parent VALUES(7); INSERT INTO child VALUES(7);')
        db.commit()
        db.execute('INSERT INTO parent VALUES(8)')  # Uncommitted data is not part of snapshot.
        snapshot(source,tmp_path/'backup.sqlite')
        db.rollback()
    snapshot(tmp_path/'backup.sqlite',tmp_path/'restored.sqlite')
    with sqlite3.connect(tmp_path/'restored.sqlite') as restored:
        assert restored.execute('SELECT id FROM parent').fetchall()==[(7,)]
        assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert restored.execute('PRAGMA foreign_key_check').fetchall()==[]
    original=(tmp_path/'restored.sqlite').read_bytes()
    with pytest.raises(FileExistsError):
        snapshot(source,tmp_path/'restored.sqlite')
    assert (tmp_path/'restored.sqlite').read_bytes()==original


def test_invalid_source_does_not_leave_destination(tmp_path):
    source=tmp_path/'bad.sqlite'
    source.write_bytes(b'not a database')
    with pytest.raises(sqlite3.DatabaseError):
        snapshot(source,tmp_path/'result.sqlite')
    assert not (tmp_path/'result.sqlite').exists()
