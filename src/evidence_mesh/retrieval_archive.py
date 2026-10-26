"""Operator-only, private acquisition records. Never semantic certification."""
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import uuid

AIP_TASK_ID = ContextVar('retrieval_aip_task_id', default=None)
AIP_TASK_TRANSPORT = ContextVar('retrieval_aip_task_transport', default=None)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')


class ArchiveCapacityError(ValueError):
    """Operator retention limit reached; old evidence must remain intact."""


class RetrievalArchive:
    def __init__(self, root, task_id=None):
        root = Path(root)
        if not root.is_absolute() or root.is_symlink() or root.resolve() != root:
            raise ValueError('Private archive root redirects')
        info = root.stat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('Private archive root missing')
        if os.name == 'posix' and (info.st_mode & 0o077 or info.st_uid != os.geteuid()):
            raise ValueError('Private archive root permissions invalid')
        # A bounded operator setting lets deployments grow without purging
        # historical evidence or disabling acquisition provenance.
        limit = os.getenv('PUBLIC_RETRIEVAL_ARCHIVE_MAX_RUNS', '64')
        if not limit.isdecimal() or not 1 <= int(limit) <= 4096:
            raise ValueError('Archive retention limit must be 1 to 4096')
        if sum(1 for _ in root.iterdir()) >= int(limit):
            raise ArchiveCapacityError('Archive retention capacity reached')
        self.run_id = uuid.uuid4().hex
        self.path = root / self.run_id
        self.path.mkdir(mode=0o700)
        self.task_id = task_id
        self.task_transport = AIP_TASK_TRANSPORT.get() if task_id else None
        self.lock = threading.Lock()
        self.records = []
        self.closed = False

    def _write(self, name, raw):
        if len(raw) > 1024 * 1024:
            raise ValueError('Archive artifact too large')
        path = self.path / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        if path.read_bytes() != raw:
            raise ValueError('Archive read-back mismatch')
        return {'file': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

    def capture(self, kind, raw, metadata):
        if kind not in ('search', 'page') or not isinstance(raw, bytes) or len(raw) > 512 * 1024:
            raise ValueError('Invalid acquisition artifact')
        with self.lock:
            if self.closed or len(self.records) >= 12:
                raise ValueError('Archive closed or capacity exceeded')
            prefix = f'{len(self.records) + 1:02d}-{kind}'
            body = self._write(prefix + '.raw', raw)
            record = {'kind': kind, 'raw': body, 'metadata': metadata,
                      'captured_at': datetime.now(timezone.utc).isoformat()}
            sidecar = self._write(prefix + '.json', encoded(record))
            self.records.append({'kind': kind, 'raw': body, 'sidecar': sidecar})

    def search(self, query, raw):
        self.capture('search', raw, {'query': query, 'response_is_evidence': False})

    def page(self, raw, document):
        if hashlib.sha256(raw).hexdigest() != document.get('body_sha256'):
            raise ValueError('Archived page hash mismatch')
        self.capture('page', raw, document)

    def finish(self, product):
        with self.lock:
            if self.closed:
                raise ValueError('Archive already finalized')
            self.closed = True  # Late timed-out reader callbacks cannot mutate a frozen run.
            output = self._write('source-product.json', encoded(product))
            manifest = {'schema_version': 'source-runtime-acquisition/1',
                        'run_id': self.run_id, 'partner_task_id': self.task_id,
                        'task_id_origin': 'aip-runtime' if self.task_id else 'not-available',
                        'task_transport': self.task_transport or 'not-recorded',
                        'claim_id': product.get('payload', {}).get('claim_id'),
                        'finished_at': datetime.now(timezone.utc).isoformat(),
                        'artifacts': self.records, 'product': output,
                        'semantic_acceptance': False, 'claim_verified': False}
            saved = self._write('manifest.json', encoded(manifest))
            return {'run_id': self.run_id, 'manifest_sha256': saved['sha256'],
                    'partner_task_id': self.task_id, 'status': 'recorded',
                    'semantic_acceptance': False}
