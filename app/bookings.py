"""Persistent booking rules shared by bot and management API."""
import sqlite3
from datetime import datetime, timezone
from .intervals import overlaps


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
    migrate_staff(db)
    return db


def migrate_staff(db):
    """Upgrade the original single-resource database without losing bookings."""
    if 'employee_id' in {row['name'] for row in db.execute('PRAGMA table_info(slots)')}:
        return
    db.execute('PRAGMA foreign_keys=OFF')
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            # Another connection may have completed the migration while we waited.
            if 'employee_id' in {row['name'] for row in db.execute('PRAGMA table_info(slots)')}:
                return
            db.execute('CREATE TABLE employees(id INTEGER PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)))')
            db.execute("INSERT INTO employees(id,name) VALUES(1,'Основной специалист')")
            db.execute('CREATE TABLE slots_v2(id INTEGER PRIMARY KEY,service_id INTEGER NOT NULL REFERENCES services(id),starts_at TEXT NOT NULL,employee_id INTEGER NOT NULL DEFAULT 1 REFERENCES employees(id),UNIQUE(employee_id,starts_at))')
            db.execute('INSERT INTO slots_v2(id,service_id,starts_at) SELECT id,service_id,starts_at FROM slots')
            db.execute('DROP TABLE slots')
            db.execute('ALTER TABLE slots_v2 RENAME TO slots')
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Migration foreign key validation failed')
            db.execute('PRAGMA user_version=2')
    finally:
        db.execute('PRAGMA foreign_keys=ON')


def interval_available(db, slot):
    start = datetime.fromisoformat(slot['starts_at'])
    duration = db.execute('SELECT duration_minutes FROM services WHERE id=?', (slot['service_id'],)).fetchone()[0]
    active = db.execute("SELECT s.starts_at,v.duration_minutes FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN services v ON v.id=s.service_id WHERE s.employee_id=? AND b.status IN('confirmed','completed')", (slot['employee_id'],)).fetchall()
    for other in active:
        other_start = datetime.fromisoformat(other['starts_at'])
        if overlaps(start, duration, other_start, other['duration_minutes']):
            return False
    return True


def available_slots(db, limit=30):
    rows = db.execute('SELECT s.*,v.title,e.name AS employee_name FROM slots s JOIN services v ON v.id=s.service_id JOIN employees e ON e.id=s.employee_id WHERE e.active=1 ORDER BY s.starts_at,s.id').fetchall()
    now = datetime.now(timezone.utc)
    result = []
    for slot in rows:
        if datetime.fromisoformat(slot['starts_at']) > now and interval_available(db, slot):
            result.append(dict(slot))
            if len(result) == limit:
                break
    return result


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
        if not db.execute('SELECT 1 FROM employees WHERE id=? AND active=1', (slot['employee_id'],)).fetchone() or not interval_available(db, slot):
            raise BookingConflict('Employee unavailable or appointment interval overlaps')
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
