"""Persistent booking rules shared by bot and management API."""
import sqlite3
from datetime import datetime, timezone, timedelta


class BookingConflict(ValueError):
    pass


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY,title TEXT NOT NULL,duration_minutes INTEGER NOT NULL CHECK(duration_minutes>0),price_kopecks INTEGER NOT NULL CHECK(price_kopecks>=0));
    CREATE TABLE IF NOT EXISTS slots(id INTEGER PRIMARY KEY,service_id INTEGER NOT NULL REFERENCES services(id),starts_at TEXT NOT NULL UNIQUE);
    CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY,telegram_user_id INTEGER NOT NULL,slot_id INTEGER NOT NULL REFERENCES slots(id),customer_name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN('confirmed','cancelled','completed')),created_at TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking_per_slot ON bookings(slot_id) WHERE status IN('confirmed','completed');
    CREATE TABLE IF NOT EXISTS processed_updates(update_id INTEGER PRIMARY KEY,result_booking_id INTEGER REFERENCES bookings(id));
    CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,admin_id INTEGER NOT NULL REFERENCES admins(id),expires_at INTEGER NOT NULL);
    """)
    return db


def book(db, user_id, slot_id, name, update_id):
    if type(user_id) is not int or user_id <= 0 or type(slot_id) is not int or slot_id <= 0:
        raise ValueError("Invalid user or slot")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValueError("Name required")
    with db:
        # Serialize the lookup and write; unique index remains final stock guard.
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT result_booking_id FROM processed_updates WHERE update_id=?", (update_id,)).fetchone()
        if previous:
            row = db.execute("SELECT * FROM bookings WHERE id=?", (previous[0],)).fetchone()
            if row["telegram_user_id"] != user_id or row["slot_id"] != slot_id:
                raise BookingConflict("Update already handled with different booking")
            return dict(row)
        slot = db.execute("SELECT * FROM slots WHERE id=?", (slot_id,)).fetchone()
        if not slot or datetime.fromisoformat(slot["starts_at"]) <= datetime.now(timezone.utc):
            raise BookingConflict("Slot unavailable")
        # One business resource. Half-open [start,end) permits back-to-back visits.
        start = datetime.fromisoformat(slot['starts_at'])
        duration = db.execute('SELECT duration_minutes FROM services WHERE id=?', (slot['service_id'],)).fetchone()[0]
        end = start + timedelta(minutes=duration)
        active = db.execute("SELECT s.starts_at,v.duration_minutes FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN services v ON v.id=s.service_id WHERE b.status IN('confirmed','completed')").fetchall()
        for other in active:
            other_start = datetime.fromisoformat(other['starts_at'])
            if start < other_start + timedelta(minutes=other['duration_minutes']) and other_start < end:
                raise BookingConflict('Appointment interval overlaps an active booking')
        try:
            cursor = db.execute("INSERT INTO bookings(telegram_user_id,slot_id,customer_name,created_at) VALUES(?,?,?,?)", (user_id,slot_id,name.strip(),datetime.now(timezone.utc).isoformat()))
            db.execute("INSERT INTO processed_updates VALUES(?,?)", (update_id,cursor.lastrowid))
        except sqlite3.IntegrityError as error:
            raise BookingConflict("Slot already booked") from error
        return dict(db.execute("SELECT * FROM bookings WHERE id=?", (cursor.lastrowid,)).fetchone())


def cancel(db, user_id, booking_id):
    with db:
        row = db.execute("SELECT * FROM bookings WHERE id=? AND telegram_user_id=?", (booking_id,user_id)).fetchone()
        if not row:
            raise BookingConflict("Booking not found")
        if row["status"] == "completed":
            raise BookingConflict("Completed booking cannot be cancelled")
        db.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
