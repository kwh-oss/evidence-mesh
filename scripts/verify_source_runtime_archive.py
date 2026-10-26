"""Read-only byte-integrity audit; never grants semantic or deployed acceptance."""
import argparse
import hashlib
import json
from pathlib import Path


def audit(directory):
    directory = Path(directory)
    if not directory.is_absolute() or directory.is_symlink() or directory.resolve() != directory:
        raise ValueError('Explicit non-redirected archive directory required')

    def artifact(record):
        name = record.get('file')
        if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Unsafe artifact filename')
        path = directory / name
        if path.is_symlink() or path.resolve() != path or not path.is_file():
            raise ValueError('Missing or redirected artifact')
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('Oversized artifact')
        raw = path.read_bytes()
        if len(raw) != record.get('bytes') or hashlib.sha256(raw).hexdigest() != record.get('sha256'):
            raise ValueError('Artifact byte/hash mismatch')
        return raw

    manifest_path = directory / 'manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError('Unsafe manifest')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 'source-runtime-acquisition/1':
        raise ValueError('Unknown manifest schema')
    if manifest.get('run_id') != directory.name:
        raise ValueError('Manifest/run directory mismatch')
    records = manifest.get('artifacts')
    if not isinstance(records, list) or len(records) > 12:
        raise ValueError('Invalid artifact list')
    product = json.loads(artifact(manifest['product']))
    queries, pages, filenames = [], {}, {manifest['product']['file'], 'manifest.json'}
    for record in records:
        raw, sidecar_raw = artifact(record['raw']), artifact(record['sidecar'])
        for name in (record['raw']['file'], record['sidecar']['file']):
            if name in filenames:
                raise ValueError('Duplicate artifact name')
            filenames.add(name)
        sidecar = json.loads(sidecar_raw)
        if sidecar.get('raw') != record['raw'] or sidecar.get('kind') != record.get('kind'):
            raise ValueError('Sidecar binding mismatch')
        metadata = sidecar['metadata']
        if record['kind'] == 'search':
            query = metadata.get('query')
            if not isinstance(query, str):
                raise ValueError('Missing recorded query')
            queries.append(query)
        elif record['kind'] == 'page':
            if metadata.get('body_sha256') != record['raw']['sha256']:
                raise ValueError('Page byte binding mismatch')
            text = metadata.get('text')
            if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != metadata.get('text_sha256'):
                raise ValueError('Page text binding mismatch')
            pages[metadata.get('url')] = metadata
        else:
            raise ValueError('Unknown artifact kind')
    actual_names = {p.name for p in directory.iterdir()}
    if actual_names != filenames:
        raise ValueError('Unlisted/missing archive entries')
    retrieval = product.get('retrieval', {})
    for page in retrieval.get('sources', []):
        recorded = pages.get(page.get('url'))
        if (not recorded or recorded.get('text_sha256') != page.get('text_sha256')
                or recorded.get('text') != page.get('text')):
            raise ValueError('Returned evidence lacks matching raw page archive')
    task_id = manifest.get('partner_task_id')
    origin = manifest.get('task_id_origin')
    if origin not in ('aip-runtime', 'not-available') or (origin == 'aip-runtime') != bool(task_id):
        raise ValueError('Task identity origin inconsistent')
    if manifest.get('claim_id') != product.get('payload', {}).get('claim_id'):
        raise ValueError('Claim identity binding mismatch')
    expected_queries = retrieval.get('queries', [])
    return {'status': 'artifact-integrity-checked', 'partner_task_id': task_id,
            'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'recorded_searches': len(queries), 'recorded_pages': len(pages),
            'all_attempted_queries_have_response': all(q in queries for q in expected_queries),
            'search_complete_reported': retrieval.get('search_complete') is True,
            'semantic_acceptance': False, 'deployed_aip_acceptance': False,
            'note': 'Integrity alone does not verify relevance, source authenticity or reasoning.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.directory), ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, KeyError):
        raise SystemExit('Archive audit failed; no secret-bearing file contents displayed.')


if __name__ == '__main__':
    main()
