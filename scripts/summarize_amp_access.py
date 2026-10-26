"""Read-only incoming task counts; unknown origin is never organic usage."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone required')
    return result


def summarize(records, aics, start, end, known_tests=()):
    if start >= end:
        raise ValueError('start must precede end')
    tasks = defaultdict(list)
    excluded = Counter()
    for row in records:
        try:
            if row.get('log_type') != 'access':
                excluded['non_access'] += 1; continue
            if row.get('aic') not in aics:
                excluded['other_identity'] += 1; continue
            when = instant(row['timestamp'])
            if not start <= when < end:
                excluded['outside_window'] += 1; continue
            body = row['body']
            # Caller-side edges are not incoming visits to the logging agent.
            if body['callee'].get('aic') != row['aic']:
                excluded['not_incoming'] += 1; continue
            task = row.get('correlation_id')
            if not isinstance(task, str) or not task.strip():
                excluded['missing_task_id'] += 1; continue
            status = body.get('response', {}).get('statusCode')
            outcome = ('http_success' if 200 <= status < 300 else 'http_failure') if type(status) is int else 'unknown'
            tasks[(row['aic'], task)].append((when, outcome))
        except (KeyError, TypeError, ValueError, AttributeError):
            excluded['invalid_record'] += 1
    agents = {}
    for aic in sorted(aics):
        counts = Counter()
        for (identity, task), events in tasks.items():
            if identity != aic: continue
            counts['unique_incoming_tasks'] += 1
            counts['known_self_test' if task in known_tests else 'unknown_origin'] += 1
            outcomes = {item[1] for item in events}
            counts[next(iter(outcomes)) if len(outcomes) == 1 else 'mixed_http_outcomes'] += 1
            counts['extra_records_for_same_task'] += len(events)-1
        agents[aic] = dict(counts)
    return {'window': {'start_inclusive': start.isoformat(), 'end_exclusive': end.isoformat()},
            'agents': agents, 'excluded': dict(excluded),
            'scope': 'supplied local logs only; HTTP success is not semantic success; unknown origin is not organic usage; missing logs cannot prove zero traffic'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, action='append', required=True)
    parser.add_argument('--aic', action='append', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--known-test-ids', type=Path, help='JSON list of confirmed self-test task IDs, not guessed prefixes')
    args = parser.parse_args()
    known = json.loads(args.known_test_ids.read_text(encoding='utf-8-sig')) if args.known_test_ids else []
    if not isinstance(known, list) or any(not isinstance(x, str) or not x.strip() for x in known):
        raise ValueError('known test IDs must be an explicit nonempty-string list')
    malformed = 0
    def rows():
        nonlocal malformed
        for path in args.log:
            with path.open(encoding='utf-8-sig') as stream:
                for line in stream:
                    if not line.strip(): continue
                    try: yield json.loads(line)
                    except json.JSONDecodeError: malformed += 1
    report = summarize(rows(), set(args.aic), instant(args.start), instant(args.end), set(known))
    report['malformed_json_lines'] = malformed
    report['input_files'] = len(args.log)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
