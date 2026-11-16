"""Copy a consistent SQLite snapshot into a NEW path; never overwrite."""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def snapshot(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination or not source.is_file():
        raise ValueError('Existing source and a different new destination required')
    with destination.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=5)) as original:
            with closing(sqlite3.connect(destination)) as target:
                original.backup(target)
                if target.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ValueError('Integrity check failed')
                if target.execute('PRAGMA foreign_key_check').fetchone():
                    raise ValueError('Foreign key check failed')
    except Exception:
        destination.unlink(missing_ok=True)  # Only the new file reserved by this call.
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore'])
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        snapshot(args.source, args.destination)
    except Exception:
        parser.exit(1, 'Snapshot failed; check source integrity and choose a new destination.\n')
    print('SQLite snapshot verified; existing files were not overwritten.')


if __name__ == '__main__':
    main()
