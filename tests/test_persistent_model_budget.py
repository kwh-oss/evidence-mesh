from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest

from evidence_mesh.model_budget import PersistentAttemptBudget


class PersistentBudgetTests(unittest.TestCase):
    def test_approved_200_to_300_keeps_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'quota.sqlite3'
            PersistentAttemptBudget(path,200)
            with closing(sqlite3.connect(path)) as db, db:db.execute('UPDATE quota SET attempts=200')
            PersistentAttemptBudget.raise_ceiling(path,expected_attempts=200,expected_ceiling=200,new_ceiling=300)
            with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('SELECT attempts,ceiling FROM quota').fetchone(),(200,300))
    def test_authorized_expansion_from_50_preserves_counter_and_cas(self):
        for target in (200, 500):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'quota.sqlite3'
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute('CREATE TABLE quota(id INTEGER PRIMARY KEY, attempts INTEGER, ceiling INTEGER CHECK(ceiling BETWEEN 1 AND 50))')
                    db.execute('INSERT INTO quota VALUES(1,49,50)')
                with self.assertRaises(ValueError):
                    PersistentAttemptBudget(path, target)
                PersistentAttemptBudget.raise_ceiling(path, expected_attempts=49, expected_ceiling=50, new_ceiling=target)
                PersistentAttemptBudget(path, target).reserve()
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(db.execute('SELECT attempts,ceiling FROM quota').fetchone(), (50,target))
                with self.assertRaises(ValueError):
                    PersistentAttemptBudget.raise_ceiling(path, expected_attempts=49, expected_ceiling=50, new_ceiling=target)

    def test_explicit_increase_preserves_old_schema_counter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'quota.sqlite3'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE quota(id INTEGER PRIMARY KEY, attempts INTEGER, ceiling INTEGER CHECK(ceiling BETWEEN 1 AND 4))')
                db.execute('INSERT INTO quota VALUES(1,4,4)')
            with self.assertRaises(ValueError):
                PersistentAttemptBudget(path, 20)
            with self.assertRaises(ValueError):
                PersistentAttemptBudget.raise_ceiling(path, expected_attempts=3, expected_ceiling=4, new_ceiling=20)
            PersistentAttemptBudget.raise_ceiling(path, expected_attempts=4, expected_ceiling=4, new_ceiling=20)
            budget = PersistentAttemptBudget(path, 20)
            budget.reserve()
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT attempts,ceiling FROM quota').fetchone(), (5,20))
            with self.assertRaises(ValueError):
                PersistentAttemptBudget.raise_ceiling(path, expected_attempts=4, expected_ceiling=4, new_ceiling=20)

    def test_restart_does_not_reset_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'quota.sqlite3'
            first = PersistentAttemptBudget(path, 2)
            first.reserve()
            second = PersistentAttemptBudget(path, 2)
            second.reserve()
            with self.assertRaises(ValueError):
                first.reserve()
            with self.assertRaises(ValueError):
                PersistentAttemptBudget(path, 2).reserve()

    def test_concurrent_instances_cannot_overdraw(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'quota.sqlite3'
            clients = [PersistentAttemptBudget(path, 4) for _ in range(8)]
            def reserve(client):
                try:
                    client.reserve()
                    return 1
                except ValueError:
                    return 0
            with ThreadPoolExecutor(max_workers=8) as executor:
                self.assertEqual(sum(executor.map(reserve, clients)), 4)

    def test_corrupt_state_and_missing_directory_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'quota.sqlite3'
            path.write_bytes(b'invalid sqlite state')
            with self.assertRaises(ValueError):
                PersistentAttemptBudget(path, 4)
            with self.assertRaises(ValueError):
                PersistentAttemptBudget(Path(directory) / 'missing' / 'quota.sqlite3', 4)

    def test_ceiling_cannot_be_enlarged_by_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'quota.sqlite3'
            PersistentAttemptBudget(path, 1)
            with self.assertRaises(ValueError):
                PersistentAttemptBudget(path, 4)
