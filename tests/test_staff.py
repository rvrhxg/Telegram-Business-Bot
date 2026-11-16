import sqlite3
import pytest
from app.bookings import connect, book, BookingConflict, available_slots


def test_staff_parallel_time_and_independent_availability(tmp_path):
    db = connect(tmp_path / 'staff.sqlite')
    try:
        with db:
            db.execute("INSERT INTO employees(id,name) VALUES(2,'Second')")
            db.execute("INSERT INTO services VALUES(1,'Visit',60,100)")
            db.executemany('INSERT INTO slots VALUES(?,?,?,?)', [(1,1,'2099-01-01T10:00:00+00:00',1),(2,1,'2099-01-01T10:00:00+00:00',2),(3,1,'2099-01-01T10:30:00+00:00',1)])
        book(db,101,1,'A',1)
        assert [slot['id'] for slot in available_slots(db)] == [2]
        book(db,102,2,'B',2)
        with pytest.raises(BookingConflict):
            book(db,103,3,'C',3)
        with db:
            db.execute('UPDATE employees SET active=0 WHERE id=1')
        assert available_slots(db) == []
    finally:
        db.close()


def test_original_database_upgrade_keeps_booking_ids_and_references(tmp_path):
    path = tmp_path / 'old.sqlite'
    old = sqlite3.connect(path)
    old.executescript("""
    CREATE TABLE services(id INTEGER PRIMARY KEY,title TEXT,duration_minutes INTEGER,price_kopecks INTEGER);
    CREATE TABLE slots(id INTEGER PRIMARY KEY,service_id INTEGER REFERENCES services(id),starts_at TEXT UNIQUE);
    CREATE TABLE bookings(id INTEGER PRIMARY KEY,telegram_user_id INTEGER,slot_id INTEGER REFERENCES slots(id),customer_name TEXT,status TEXT,created_at TEXT);
    INSERT INTO services VALUES(1,'Visit',30,100);
    INSERT INTO slots VALUES(7,1,'2099-01-01T10:00:00+00:00');
    INSERT INTO bookings VALUES(9,101,7,'Customer','confirmed','2026-01-01');
    """)
    old.close()
    db = connect(path)
    try:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert db.execute('SELECT employee_id FROM slots WHERE id=7').fetchone()[0] == 1
        assert db.execute('SELECT slot_id FROM bookings WHERE id=9').fetchone()[0] == 7
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        with db:
            db.execute("INSERT INTO employees(id,name) VALUES(2,'Second')")
            db.execute("INSERT INTO slots(service_id,starts_at,employee_id) VALUES(1,'2099-01-01T10:00:00+00:00',2)")
    finally:
        db.close()
