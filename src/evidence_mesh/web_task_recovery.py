"""Private durable task identities and one-shot completion admission. No Start replay."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time


class WebTaskRecovery:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS web_tasks '
                '(task TEXT PRIMARY KEY, session TEXT NOT NULL, observing INTEGER NOT NULL, '
                'completion_claimed INTEGER NOT NULL DEFAULT 0, result TEXT, created REAL NOT NULL)')

    def register(self, task, session, observing):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO web_tasks(task,session,observing,created) VALUES(?,?,?,?)',
                       (task, session, int(observing), time.time()))

    def read(self, task):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT session,observing,completion_claimed,result FROM web_tasks WHERE task=?', (task,)).fetchone()
        return None if row is None else {'task': task, 'session': row[0], 'observing': bool(row[1]),
            'completion_claimed': bool(row[2]), 'result': json.loads(row[3]) if row[3] else None}

    def claim_completion(self, task):
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute('UPDATE web_tasks SET completion_claimed=1 WHERE task=? AND completion_claimed=0',
                              (task,)).rowcount == 1

    def finish(self, task, result):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE web_tasks SET result=? WHERE task=?',
                       (json.dumps(result, ensure_ascii=False), task))
