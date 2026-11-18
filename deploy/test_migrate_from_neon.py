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
elif 'exec' in args or 'run' in args:
    command = ' '.join(args)
    if 'server_version_num' in command:
        assert 'run' in args and 'postgres:18-alpine' in args and '--rm' in args
        print('190001' if scenario == 'newer_source' else os.environ.get('SOURCE_VERSION', '160005'))
    elif 'pg_dump' in command:
        assert 'run' in args and 'postgres:18-alpine' in args and '--rm' in args
        print(os.environ.get('DUMP_SQL', 'CREATE TABLE example (id integer);'))
        if scenario == 'dump_failure':
            sys.exit(1)
    elif 'pg_class' in command:
        print('1' if scenario == 'nonempty' else '0')
    elif '--single-transaction' in args:
        assert '--file=-' in args
        assert 'ON_ERROR_STOP=1' in command
        assert 'db' in args and 'run' not in args
        Path(os.environ['RESTORED_SQL']).write_text(sys.stdin.read())
        if scenario == 'restore_failure':
            sys.exit(1)
'''


class NeonMigrationTests(unittest.TestCase):
    def run_migration(self, scenario, source_stopped=True, source_version='160005', dump_sql=None):
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
                   SOURCE_WRITES_STOPPED='yes' if source_stopped else 'no',
                   SOURCE_VERSION=source_version, RESTORED_SQL=str(root / 'restored.sql'))
        if dump_sql is not None:
            env['DUMP_SQL'] = dump_sql
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
        self.assertEqual((root / 'restored.sql').read_text(), dump.read_text())
        self.assertEqual(Path(str(dump) + '.restore').stat().st_mode & 0o777, 0o600)
        self.assertEqual(sum('--single-transaction' in call for call in calls), 1)
        dump_call, = [call for call in calls if 'pg_dump' in ' '.join(call)]
        for option in ('--no-owner', '--no-acl', '--format=plain'):
            self.assertIn(option, ' '.join(dump_call))

    def test_source_versions_16_17_18_are_supported(self):
        for version in ('160005', '170003', '180001'):
            with self.subTest(version=version):
                _, result, _ = self.run_migration('success', source_version=version)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_filters_neon_metadata_without_changing_copy_data_or_function_bodies(self):
        dump_sql = r'''SET transaction_timeout = 0;
-- Name: example; Type: FUNCTION; Schema: public; Owner: app
CREATE FUNCTION example() RETURNS void AS $body$
BEGIN
SET transaction_timeout = 42;
GRANT SELECT ON example TO neon;
END;
$body$ LANGUAGE plpgsql;
-- Name: example; Type: TABLE; Schema: public; Owner: app
CREATE TABLE example (value text);
COPY public.example (value) FROM stdin;
SET transaction_timeout = 99;
ALTER DEFAULT PRIVILEGES FOR ROLE neon GRANT SELECT ON TABLES TO app;
GRANT SELECT ON example TO neon;
REVOKE SELECT ON example FROM neon;
\.
-- Name: example; Type: ACL; Schema: public; Owner: app
GRANT SELECT ON example TO neon;
GRANT SELECT ON example
    TO "neondb_owner";
REVOKE SELECT ON example FROM neon_superuser;
GRANT SELECT ON example TO app;
-- Name: DEFAULT PRIVILEGES; Type: DEFAULT ACL; Schema: public; Owner: neon
ALTER DEFAULT PRIVILEGES FOR ROLE neon
    GRANT SELECT ON TABLES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE "neondb_owner" GRANT ALL ON TABLES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE app GRANT SELECT ON TABLES TO reader;'''
        root, result, _ = self.run_migration('success', source_version='180001', dump_sql=dump_sql)
        self.assertEqual(result.returncode, 0, result.stderr)
        restored = (root / 'restored.sql').read_text()
        self.assertNotIn('SET transaction_timeout = 0;', restored)
        self.assertIn('SET transaction_timeout = 42;', restored)
        self.assertIn('GRANT SELECT ON example TO app;', restored)
        self.assertIn('ALTER DEFAULT PRIVILEGES FOR ROLE app', restored)
        self.assertNotIn('TO "neondb_owner";', restored)
        self.assertNotIn('FROM neon_superuser;', restored)
        self.assertNotIn('FOR ROLE "neondb_owner"', restored)
        self.assertEqual(restored.count('GRANT SELECT ON example TO neon;'), 2)
        self.assertIn(dump_sql.split('COPY ')[1].split(r'\.')[0], restored)
        self.assertEqual(restored.count('ALTER DEFAULT PRIVILEGES FOR ROLE neon'), 1)
        dump, = (root / 'deploy/backups').glob('*.sql')
        self.assertEqual(dump.read_text(), dump_sql + '\n')
        checksums = Path(str(dump) + '.sha256').read_text().splitlines()
        self.assertEqual(checksums[1].split()[0], hashlib.sha256(restored.encode()).hexdigest())

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
