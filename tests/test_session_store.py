import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('store', Path(__file__).parents[1] / 'scripts/session_store.py')
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


def payload(week=1, before=40):
    start, end = ('2026-01-05', '2026-01-11') if week == 1 else ('2026-01-12', '2026-01-18')
    return {'week': week, 'date_start': start, 'date_end': end, 'rating': 4,
            'source': 'Test conversation, accepted closing',
            'stats': [{'id': 'rest', 'label': '🔥 Rest', 'before': before, 'delta': 1,
                       'after': before + 1, 'criterion_version': 'v1', 'evidence': 'Reported action'}],
            'artifacts': {f'week{week}_log.md': f'# Week {week}\nEvent\n',
                          'character_sheet.md': f'# Sheet\n- 🔥 Rest: {before + 1}\n',
                          'achievements.md': '# Achievements\n', 'supports.md': '# Supports\n'}}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, p):
        store.draft(self.root, p)
        store.validate(self.root, p['week'])
        store.commit(self.root, p['week'])
        store.validate(self.root, p['week'])

    def test_incomplete_draft_resumes_without_touching_totals(self):
        store.draft(self.root, {'week': 1, 'notes': {'facts': ['A useful event']}})
        self.assertFalse((self.root / 'history.csv').exists())
        self.assertEqual(store.load_record(self.root, 1)['payload']['notes']['facts'], ['A useful event'])
        self.save(payload())

    def test_idempotent_and_old_commit_never_rolls_back_new_session(self):
        self.save(payload())
        self.save(payload(2, 41))
        before = (self.root / 'character_sheet.md').read_text()
        store.commit(self.root, 1)
        store.validate(self.root, 1)
        self.assertEqual((self.root / 'character_sheet.md').read_text(), before)
        self.assertEqual(len(store.history_rows(store.read(self.root / 'history.csv'))[1]), 2)

    def test_interruption_at_every_atomic_write_recovers(self):
        # prepared journal, four Markdown targets, CSV, complete journal
        for fail_at in range(1, 8):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                store.draft(root, payload())
                actual, count = store.atomic_write, [0]
                def fail(path, content):
                    count[0] += 1
                    if count[0] == fail_at:
                        raise OSError('simulated interruption')
                    return actual(path, content)
                with patch.object(store, 'atomic_write', side_effect=fail):
                    with self.assertRaises(OSError):
                        store.commit(root, 1)
                store.commit(root, 1)
                store.validate(root, 1)
                self.assertEqual(len(store.history_rows(store.read(root / 'history.csv'))[1]), 1)

    def test_user_edit_after_draft_is_not_overwritten(self):
        store.draft(self.root, payload())
        (self.root / 'supports.md').write_text('User edit')
        with self.assertRaisesRegex(ValueError, 'changed'):
            store.commit(self.root, 1)
        self.assertEqual((self.root / 'supports.md').read_text(), 'User edit')
        self.assertFalse((self.root / 'week1_log.md').exists())

    def test_conflicting_edit_during_recovery_prevents_further_writes(self):
        store.draft(self.root, payload())
        actual = store.atomic_write
        def stop(path, content):
            if path.name == 'character_sheet.md':
                raise OSError('interrupted')
            return actual(path, content)
        with patch.object(store, 'atomic_write', side_effect=stop):
            with self.assertRaises(OSError):
                store.commit(self.root, 1)
        (self.root / 'character_sheet.md').write_text('User edited sheet')
        with self.assertRaisesRegex(ValueError, 'conflict'):
            store.commit(self.root, 1)
        self.assertFalse((self.root / 'history.csv').exists())
        self.assertEqual((self.root / 'character_sheet.md').read_text(), 'User edited sheet')

    def test_rejects_inconsistent_or_unsafe_payloads(self):
        for kind in ['arithmetic', 'sheet', 'dates', 'rating', 'path', 'nonfinite', 'duplicate_stat', 'missing_version']:
            with self.subTest(kind=kind):
                p = payload()
                if kind == 'arithmetic': p['stats'][0]['after'] = 42
                if kind == 'sheet': p['artifacts']['character_sheet.md'] = '- 🔥 Rest: 90\n'
                if kind == 'dates': p['date_end'] = '2026-01-01'
                if kind == 'rating': p['rating'] = 9
                if kind == 'path': p['artifacts']['../escape.md'] = 'unsafe'
                if kind == 'nonfinite': p['stats'][0]['delta'] = float('nan')
                if kind == 'duplicate_stat': p['stats'].append(copy.deepcopy(p['stats'][0]))
                if kind == 'missing_version': p['stats'][0]['criterion_version'] = ''
                with self.assertRaises(ValueError): store.build(p, None)

    def test_preserves_legacy_history_and_validates_previous_total(self):
        legacy = 'week,date_start,date_end,rating,rest\n1,2026-01-05,2026-01-11,2-3,41\n'
        (self.root / 'history.csv').write_text(legacy)
        self.save(payload(2, 41))
        self.assertIn('2-3,41', (self.root / 'history.csv').read_text())
        with self.assertRaisesRegex(ValueError, 'before differs'):
            store.build(payload(2, 100), legacy)

    def test_rejects_duplicate_week_and_overlapping_dates(self):
        self.save(payload())
        history = store.read(self.root / 'history.csv')
        with self.assertRaisesRegex(ValueError, 'week must follow'):
            store.build(payload(), history)
        p = payload(2, 41)
        p['date_start'] = '2026-01-11'
        with self.assertRaisesRegex(ValueError, 'start after'):
            store.build(p, history)

    def test_preserves_criterion_versions_without_rescoring(self):
        self.save(payload())
        p = payload(2, 41)
        p['stats'][0]['criterion_version'] = 'v2'
        p['artifacts']['profile.md'] = '# Criteria\nv1: first week; v2: effective week 2\n'
        self.save(p)
        self.assertEqual(store.load_record(self.root, 1)['payload']['stats'][0]['criterion_version'], 'v1')
        self.assertEqual(store.load_record(self.root, 2)['payload']['stats'][0]['before'], 41)

    def test_existing_unindexed_log_requires_reconciliation(self):
        (self.root / 'week1_log.md').write_text('Previously saved session')
        store.draft(self.root, payload())
        with self.assertRaisesRegex(ValueError, 'existing week log'):
            store.commit(self.root, 1)
        self.assertEqual((self.root / 'week1_log.md').read_text(), 'Previously saved session')

    def test_blocks_multiple_unfinished_sessions(self):
        store.draft(self.root, {'week': 1})
        with self.assertRaisesRegex(ValueError, 'existing draft'):
            store.draft(self.root, {'week': 2})

    def test_detects_completed_artifact_and_record_tampering(self):
        self.save(payload())
        (self.root / 'supports.md').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'artifact differs'):
            store.validate(self.root, 1)
        record = store.load_record(self.root, 1)
        record['payload']['source'] = 'changed source'
        store.record_path(self.root, 1).write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            store.commit(self.root, 1)

    def test_new_stat_requires_explicit_baseline_and_profile(self):
        history = 'week,date_start,date_end,rating,rest,new_stat\n1,2026-01-05,2026-01-11,4,41,\n'
        p = payload(2, 41)
        p['stats'].append({'id': 'new_stat', 'label': 'New stat', 'before': 20,
                           'delta': 0, 'after': 20, 'criterion_version': 'v1',
                           'evidence': 'Initial baseline'})
        p['artifacts']['character_sheet.md'] += '- New stat: 20\n'
        with self.assertRaisesRegex(ValueError, 'authorized baseline'):
            store.build(p, history)
        p['stats'][-1]['baseline_reason'] = 'User chose symbolic baseline 20'
        p['artifacts']['profile.md'] = '# Profile\nNew stat criteria v1, effective session 2\n'
        result = store.build(p, history)
        self.assertIn('1,2026-01-05,2026-01-11,4,41,\n', result['history.csv'])

    def test_unknown_observation_keeps_total(self):
        p = payload()
        p['stats'][0].update(delta=0, after=40, evidence='Unknown this session; unchanged')
        p['artifacts']['character_sheet.md'] = '- 🔥 Rest: 40\n'
        self.save(p)
        self.assertEqual(store.history_rows(store.read(self.root / 'history.csv'))[1][0]['rest'], '40')

    def test_process_lock_prevents_concurrent_writers(self):
        with store.lock(self.root):
            with self.assertRaises(BlockingIOError):
                with store.lock(self.root):
                    self.fail('second writer acquired lock')

    def test_symlink_destination_refused(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / 'untouched'
            target.write_text('outside')
            (self.root / 'supports.md').symlink_to(target)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                store.draft(self.root, payload())
            self.assertEqual(target.read_text(), 'outside')


if __name__ == '__main__':
    unittest.main()
