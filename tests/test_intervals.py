import pytest
from app.bookings import connect, book, cancel, BookingConflict


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / 'intervals.sqlite')
    with connection:
        connection.executemany('INSERT INTO services VALUES(?,?,?,?)', [(1,'Short',30,100),(2,'Long',90,200)])
        connection.executemany('INSERT INTO slots VALUES(?,?,?)', [
            (1,1,'2099-01-01T10:00:00+00:00'),
            (2,1,'2099-01-01T10:15:00+00:00'),
            (3,2,'2099-01-01T09:30:00+00:00'),
            (4,1,'2099-01-01T10:30:00+00:00'),
            (5,1,'2099-01-01T09:45:00+00:00'),
            (6,1,'2099-01-01T13:00:00+03:00')])
    yield connection
    connection.close()


@pytest.mark.parametrize('candidate', [2,3,5,6])
def test_partial_containment_reverse_and_timezone_overlap(db, candidate):
    book(db,101,1,'A',1)
    with pytest.raises(BookingConflict):
        book(db,102,candidate,'B',2)
    assert db.execute('SELECT count(*) FROM bookings').fetchone()[0] == 1


def test_adjacent_allowed_and_cancellation_releases_interval(db):
    first = book(db,101,1,'A',1)
    book(db,102,4,'B',2)
    cancel(db,101,first['id'])
    book(db,103,5,'C',3)


def test_completed_appointment_still_reserves_interval(db):
    first = book(db,101,1,'A',1)
    with db:
        db.execute("UPDATE bookings SET status='completed' WHERE id=?", (first['id'],))
    with pytest.raises(BookingConflict):
        book(db,102,2,'B',2)


def test_concurrent_overlapping_slots_allow_only_one_booking(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    path = tmp_path / 'race.sqlite'
    setup = connect(path)
    with setup:
        setup.execute("INSERT INTO services VALUES(1,'Visit',60,100)")
        setup.executemany('INSERT INTO slots VALUES(?,1,?)',[(1,'2099-01-01T10:00:00+00:00'),(2,'2099-01-01T10:30:00+00:00')])
    setup.close()
    barrier = Barrier(2)

    def attempt(slot):
        connection = connect(path)
        try:
            barrier.wait(timeout=10)
            try:
                book(connection,100+slot,slot,'Customer',slot)
                return True
            except BookingConflict:
                return False
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt,[1,2])) == [False,True]
    check = connect(path)
    try:
        assert check.execute('SELECT count(*) FROM bookings').fetchone()[0] == 1
    finally:
        check.close()
