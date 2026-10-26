"""Durable attempt quota for the initial model deployment, containing no inputs."""
from pathlib import Path
from contextlib import closing
import sqlite3


class BudgetExhausted(ValueError):
    """Configured attempt ceiling was reached; no request was dispatched."""


class BudgetUnavailable(ValueError):
    """Attempt reservation could not be checked safely."""


class PersistentAttemptBudget:
    def __init__(self, path, limit):
        self.path = Path(path)
        if not self.path.is_absolute() or type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError('Persistent model preparation budget configuration is invalid')
        try:
            exists = self.path.exists()
            with closing(sqlite3.connect(str(self.path), timeout=5)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                if not exists:
                    db.execute('CREATE TABLE quota (id INTEGER PRIMARY KEY CHECK(id=1), '
                               'attempts INTEGER NOT NULL CHECK(attempts>=0), '
                               'ceiling INTEGER NOT NULL CHECK(ceiling BETWEEN 1 AND 500))')
                    db.execute('INSERT INTO quota VALUES (1, 0, ?)', (limit,))
                row = db.execute('SELECT attempts, ceiling FROM quota WHERE id=1').fetchone()
                if row is None or type(row[0]) is not int or type(row[1]) is not int:
                    raise ValueError('invalid quota')
                if not 0 <= row[0] <= row[1] <= 500 or limit > row[1]:
                    raise ValueError('quota cannot be enlarged automatically')
                # Decreasing a configured ceiling remains effective after restart.
                if row[0] > limit:
                    raise ValueError('quota already exceeds requested ceiling')
                db.execute('UPDATE quota SET ceiling=? WHERE id=1', (limit,))
        except (OSError, sqlite3.Error, ValueError):
            raise ValueError('Persistent model budget is unavailable or invalid') from None

    @staticmethod
    def raise_ceiling(path, *, expected_attempts, expected_ceiling, new_ceiling):
        """Explicit operator action; compare-and-swap, never resets attempts."""
        path = Path(path)
        if (not path.is_absolute() or not path.is_file()
                or any(type(v) is not int for v in (expected_attempts, expected_ceiling, new_ceiling))
                or not 0 <= expected_attempts <= expected_ceiling < new_ceiling <= 500):
            raise ValueError('Invalid explicit budget increase')
        with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=5)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT attempts, ceiling FROM quota WHERE id=1').fetchone()
            if row != (expected_attempts, expected_ceiling):
                raise ValueError('Budget changed; inspect actual state before retrying')
            # Migrate the original CHECK ceiling<=4 without deleting/resetting its counter.
            db.execute('CREATE TABLE quota_expanded (id INTEGER PRIMARY KEY CHECK(id=1), '
                       'attempts INTEGER NOT NULL CHECK(attempts>=0), '
                       'ceiling INTEGER NOT NULL CHECK(ceiling BETWEEN 1 AND 500))')
            db.execute('INSERT INTO quota_expanded VALUES (1, ?, ?)', (row[0], new_ceiling))
            db.execute('DROP TABLE quota')
            db.execute('ALTER TABLE quota_expanded RENAME TO quota')

    def reserve(self):
        try:
            with closing(sqlite3.connect(str(self.path), timeout=5)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                changed = db.execute('UPDATE quota SET attempts=attempts+1 '
                                     'WHERE id=1 AND attempts<ceiling').rowcount
                if changed != 1:
                    raise BudgetExhausted('quota exhausted')
        except BudgetExhausted:
            raise
        except (OSError, sqlite3.Error, ValueError):
            raise BudgetUnavailable('Persistent attempt budget unavailable') from None
