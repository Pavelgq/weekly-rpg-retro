#!/usr/bin/env python3
"""Recoverable, conflict-checked campaign saves. Python 3.9+, POSIX, no dependencies."""
import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from contextlib import contextmanager

BASE = ['week', 'date_start', 'date_end', 'rating']
OPTIONAL = {'profile.md', 'supports.md', 'gm_feedback.md'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(content):
    return None if content is None else hashlib.sha256(content.encode('utf-8')).hexdigest()


def read(path):
    return path.read_text(encoding='utf-8') if path.exists() else None


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.retro-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def record_path(root, week):
    require(type(week) is int and week > 0, 'week must be a positive integer')
    return root / '.retro' / 'sessions' / ('week%d.json' % week)


def safe(root, name):
    path = root / name
    require(not path.is_symlink(), 'symlink target refused: ' + name)
    require(path.resolve().is_relative_to(root.resolve()), 'path outside campaign: ' + name)
    return path


@contextmanager
def lock(root):
    root.mkdir(parents=True, exist_ok=True)
    safe(root, '.retro')
    (root / '.retro').mkdir(exist_ok=True)
    safe(root, '.retro/sessions')
    with safe(root, '.retro/lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def same_num(a, b):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-9)


def history_rows(content):
    if not content:
        return [], []
    reader = csv.DictReader(io.StringIO(content))
    fields = reader.fieldnames
    require(fields is not None and fields[:4] == BASE and len(fields) == len(set(fields)), 'invalid history columns')
    rows = list(reader)
    last_week, last_end = 0, None
    for row in rows:
        require(None not in row and all(v is not None for v in row.values()), 'malformed history row')
        week = int(row['week'])
        start, end = dt.date.fromisoformat(row['date_start']), dt.date.fromisoformat(row['date_end'])
        require(week == last_week + 1 and start <= end, 'duplicate/missing week or invalid dates in history')
        require(last_end is None or start == last_end + dt.timedelta(days=1), 'noncontiguous history dates')
        # Preserve legacy ratings such as "2-3" without inventing a number.
        for key in fields[4:]:
            require(row[key] == '' or math.isfinite(float(row[key])), 'invalid historical stat')
        last_week, last_end = week, end
    return fields, rows


def build(payload, history):
    week = payload['week']
    record_path(Path('.'), week)
    start = dt.date.fromisoformat(payload['date_start'])
    end = dt.date.fromisoformat(payload['date_end'])
    require(start <= end, 'reversed date range')
    rating = payload.get('rating')
    require(rating is None or (number(rating) and 1 <= rating <= 5), 'rating must be 1..5 or null')
    require(isinstance(payload.get('source'), str) and payload['source'].strip(), 'source required')
    stats = payload['stats']
    require(isinstance(stats, list) and stats, 'stats required')
    columns = [s['id'] for s in stats]
    require(len(columns) == len(set(columns)) and all(re.fullmatch(r'[a-z][a-z0-9_]*', c) and c not in BASE for c in columns), 'invalid stat IDs')
    fields, rows = history_rows(history)
    require(week == (int(rows[-1]['week']) + 1 if rows else 1), 'week must follow completed history')
    if rows:
        require(start == dt.date.fromisoformat(rows[-1]['date_end']) + dt.timedelta(days=1), 'session must start after previous end')
        require(fields[4:] == columns, 'stat schema changed: explicitly migrate history columns first, preserving old values')
    else:
        fields = BASE + columns
    files = payload['artifacts']
    required = {'week%d_log.md' % week, 'character_sheet.md', 'achievements.md'}
    require(isinstance(files, dict) and required <= files.keys() <= required | OPTIONAL, 'invalid or missing artifact names')
    require(all(isinstance(v, str) and v.strip() for v in files.values()), 'artifacts must be nonempty text')
    for stat in stats:
        require(all(number(stat.get(k)) for k in ('before', 'delta', 'after')), 'finite stat numbers required')
        require(-2 <= stat['delta'] <= 3, 'delta outside -2..3')
        require(same_num(stat['before'] + stat['delta'], stat['after']), 'stat arithmetic mismatch: ' + stat['id'])
        if rows:
            if rows[-1][stat['id']] == '':
                require('profile.md' in files and isinstance(stat.get('baseline_reason'), str) and stat['baseline_reason'].strip(), 'new stat requires authorized baseline reason and profile')
            else:
                require(same_num(rows[-1][stat['id']], stat['before']), 'before differs from history: ' + stat['id'])
        require(isinstance(stat.get('criterion_version'), str) and stat['criterion_version'].strip(), 'criterion version required')
        require(isinstance(stat.get('evidence'), str) and stat['evidence'].strip(), 'evidence or explicit unknown required')
        label = stat.get('label', '')
        require(isinstance(label, str) and label.strip() and '\n' not in label, 'stat label required')
        matches = re.findall(r'^- ' + re.escape(label) + r':\s*(-?\d+(?:\.\d+)?)\b', files['character_sheet.md'], re.M)
        require(len(matches) == 1 and same_num(matches[0], stat['after']), 'character sheet total mismatch: ' + stat['id'])
    row = dict(zip(BASE, [str(week), start.isoformat(), end.isoformat(), '' if rating is None else str(rating)]))
    row.update({s['id']: str(s['after']) for s in stats})
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows + [row])
    return {**files, 'history.csv': buf.getvalue()}


def load_record(root, week):
    path = record_path(root, week)
    require(path.exists(), 'session record not found')
    data = json.loads(path.read_text(encoding='utf-8'))
    require(data.get('schema_version') == 1 and data.get('week') == week, 'invalid record')
    return data


def draft(root, payload):
    """Checkpoint may be incomplete. Completed files remain untouched."""
    week = payload['week']
    path = record_path(root, week)
    for other in (root / '.retro' / 'sessions').glob('week*.json'):
        r = json.loads(other.read_text(encoding='utf-8'))
        require(r['week'] == week or r['status'] == 'complete', 'finish existing draft/prepared session first')
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    require(not old or old['status'] == 'draft', 'prepared/completed record cannot be replaced')
    names = {'week%d_log.md' % week, 'character_sheet.md', 'achievements.md', 'history.csv'} | OPTIONAL
    baseline = old['baseline'] if old else {n: read(safe(root, n)) for n in sorted(names)}
    for name, content in baseline.items():
        require(read(safe(root, name)) == content, 'campaign changed since draft: ' + name)
    record = {'schema_version': 1, 'week': week, 'status': 'draft', 'payload': payload, 'baseline': baseline}
    atomic_write(path, dump(record))
    return record


def validate_plan(record):
    require(record['status'] in ('prepared', 'complete'), 'not a prepared save')
    targets = build(record['payload'], record['baseline']['history.csv'])
    require(targets == record['targets'] and digest(dump(record['payload'])) == record['payload_sha256'], 'prepared record integrity error')
    return targets


def commit(root, week):
    record = load_record(root, week)
    path = record_path(root, week)
    if record['status'] == 'complete':
        validate_plan(record)
        return record  # Idempotent even after later weeks; never roll back the sheet.
    if record['status'] == 'draft':
        targets = build(record['payload'], record['baseline']['history.csv'])
        # Existing log with no matching history is a missing-session conflict, not disposable.
        require(record['baseline']['week%d_log.md' % week] is None, 'existing week log must be reconciled first')
        for name, old in record['baseline'].items():
            require(read(safe(root, name)) == old, 'campaign changed since draft: ' + name)
        record.update(status='prepared', targets=targets, payload_sha256=digest(dump(record['payload'])))
        atomic_write(path, dump(record))
    targets = validate_plan(record)
    # Preflight every destination before writing any: keep unrelated/user edits.
    for name, old in record['baseline'].items():
        current = read(safe(root, name))
        require(current == old or (name in targets and current == targets[name]), 'recovery conflict: ' + name)
    for name, content in targets.items():
        if read(safe(root, name)) != content:
            atomic_write(safe(root, name), content)
    require(all(read(safe(root, n)) == text for n, text in targets.items()), 'post-save verification failed')
    record['status'] = 'complete'
    atomic_write(path, dump(record))
    return record


def validate(root, week):
    record = load_record(root, week)
    if record['status'] == 'draft':
        build(record['payload'], record['baseline']['history.csv'])
        for n, old in record['baseline'].items():
            require(read(safe(root, n)) == old, 'campaign changed since draft: ' + n)
    else:
        targets = validate_plan(record)
        require(record['status'] == 'complete', 'prepared save needs recovery')
        # Only the latest completed session should match mutable aggregate files.
        _, rows = history_rows(read(root / 'history.csv'))
        require(rows and int(rows[-1]['week']) >= week, 'history missing completed session')
        _, expected = history_rows(targets['history.csv'])
        require(rows[week - 1] == expected[-1], 'saved history row differs')
        require(read(root / ('week%d_log.md' % week)) == targets['week%d_log.md' % week], 'saved log differs')
        if int(rows[-1]['week']) == week:
            require(all(read(safe(root, n)) == text for n, text in targets.items()), 'saved artifact differs')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['draft', 'validate', 'commit', 'recover', 'status'])
    parser.add_argument('--campaign', required=True, type=Path)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--week', type=int)
    args = parser.parse_args()
    root = args.campaign.resolve()
    try:
        with lock(root):
            if args.command == 'status':
                records = [json.loads(p.read_text(encoding='utf-8')) for p in (root / '.retro' / 'sessions').glob('week*.json')]
                print(dump([{'week': r['week'], 'status': r['status']} for r in sorted(records, key=lambda r: r['week'])]))
                return
            if args.command == 'draft':
                require(args.input is not None, '--input required')
                record = draft(root, json.loads(args.input.read_text(encoding='utf-8')))
            else:
                require(args.week is not None, '--week required')
                record = validate(root, args.week) if args.command == 'validate' else commit(root, args.week)
            print('Week %d: %s (%s succeeded)' % (record['week'], record['status'], args.command))
    except (ValueError, KeyError, TypeError, OSError, csv.Error) as exc:
        parser.exit(1, 'Not saved/validated: %s\n' % exc)


if __name__ == '__main__':
    main()
