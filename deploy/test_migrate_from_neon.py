import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


MOCK_DOCKER = r'''import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\n')
scenario = os.environ['SCENARIO']
if 'ps' in args:
    print('db\nnode_api' if scenario == 'running' else 'db')
elif 'exec' in args:
    command = ' '.join(args)
    if 'server_version_num' in command:
        print('170001' if scenario == 'newer_source' else '160005')
    elif 'pg_dump' in command:
        print('CREATE TABLE example (id integer);')
        if scenario == 'dump_failure':
            sys.exit(1)
    elif 'pg_class' in command:
        print('1' if scenario == 'nonempty' else '0')
    elif '--single-transaction' in args:
        assert '--file=-' in args
        assert 'ON_ERROR_STOP=1' in command
        assert sys.stdin.read() == 'CREATE TABLE example (id integer);\n'
        if scenario == 'restore_failure':
            sys.exit(1)
'''


class NeonMigrationTests(unittest.TestCase):
    def run_migration(self, scenario, source_stopped=True):
        tmp = tempfile.TemporaryDirectory(prefix='merts-migration-test-')
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'deploy').mkdir()
        script = root / 'deploy/migrate_from_neon.sh'
        shutil.copyfile(Path(__file__).with_name('migrate_from_neon.sh'), script)
        binary = root / 'docker'
        binary.write_text(f'#!{sys.executable}\n' + MOCK_DOCKER)
        binary.chmod(0o700)
        log = root / 'calls.jsonl'
        env = dict(os.environ, PATH=f'{root}:{os.environ["PATH"]}',
                   NEON_DATABASE_URL='postgresql://user:secret@source/app?sslmode=require',
                   CALL_LOG=str(log), SCENARIO=scenario,
                   SOURCE_WRITES_STOPPED='yes' if source_stopped else 'no')
        result = subprocess.run(['bash', str(script)], env=env, text=True, capture_output=True)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        self.assertNotIn(env['NEON_DATABASE_URL'], result.stdout + result.stderr)
        return root, result, calls

    def test_success_keeps_private_dump_and_checksum_and_restores_atomically(self):
        root, result, calls = self.run_migration('success')
        self.assertEqual(result.returncode, 0, result.stderr)
        dump, = (root / 'deploy/backups').glob('*.sql')
        self.assertEqual(dump.stat().st_mode & 0o777, 0o600)
        expected = hashlib.sha256(dump.read_bytes()).hexdigest()
        self.assertEqual(Path(str(dump) + '.sha256').read_text().split()[0], expected)
        self.assertEqual(sum('--single-transaction' in call for call in calls), 1)
        dump_call, = [call for call in calls if 'pg_dump' in ' '.join(call)]
        for option in ('--no-owner', '--no-acl', '--format=plain'):
            self.assertIn(option, ' '.join(dump_call))

    def test_preflight_refuses_without_touching_dump_or_target(self):
        for scenario in ('running', 'nonempty', 'newer_source'):
            with self.subTest(scenario=scenario):
                root, result, calls = self.run_migration(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(list((root / 'deploy/backups').glob('*.sql')))
                self.assertFalse(any('--single-transaction' in call for call in calls))

    def test_source_writes_must_be_stopped(self):
        _, result, calls = self.run_migration('success', source_stopped=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_dump_failure_never_starts_restore(self):
        root, result, calls = self.run_migration('dump_failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(list((root / 'deploy/backups').glob('*.sql'))), 1)
        self.assertFalse(any('--single-transaction' in call for call in calls))

    def test_restore_failure_keeps_completed_dump_for_recovery(self):
        root, result, calls = self.run_migration('restore_failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(list((root / 'deploy/backups').glob('*.sha256'))), 1)
        self.assertIn('Migration failed', result.stderr)
        self.assertFalse(any('ANALYZE' in call for call in calls))


if __name__ == '__main__':
    unittest.main()
