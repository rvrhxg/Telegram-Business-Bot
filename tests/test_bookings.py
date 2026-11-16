import tempfile
import unittest
from pathlib import Path
from app.bookings import BookingConflict, book, cancel, connect


class BookingTests(unittest.TestCase):
    def test_double_booking_replay_ownership_and_cancellation(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = connect(Path(temporary) / "bookings.sqlite")
            try:
                with db:
                    db.execute("INSERT INTO services VALUES(1,'Консультация',30,150000)")
                    db.execute("INSERT INTO slots(id,service_id,starts_at) VALUES(1,1,'2099-01-01T10:00:00+00:00')")
                first = book(db,101,1,"Customer",1001)
                self.assertEqual(book(db,101,1,"Customer",1001)["id"],first["id"])
                with self.assertRaises(BookingConflict):
                    book(db,102,1,"Other",1002)
                with self.assertRaises(BookingConflict):
                    cancel(db,102,first["id"])
                cancel(db,101,first["id"])
                cancel(db,101,first["id"])
                self.assertNotEqual(book(db,102,1,"Other",1003)["id"],first["id"])
            finally:
                db.close()
