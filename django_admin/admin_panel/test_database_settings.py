import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class DatabaseSSLSettingsTests(unittest.TestCase):
    def test_ssl_defaults_and_explicit_modes(self):
        cases = [
            ('db', '', None),
            ('localhost', '', None),
            ('127.0.0.1', '', None),
            ('ep-example.neon.tech', '', 'require'),
            ('db', '?sslmode=require', 'require'),
            ('localhost', '?sslmode=disable', 'disable'),
            ('ep-example.neon.tech', '?sslmode=verify-full', 'verify-full'),
            ('ep-example.neon.tech', '?sslmode=disable', 'disable'),
        ]
        for host, query, expected in cases:
            with self.subTest(host=host, query=query):
                env = dict(os.environ, SECRET_KEY='x' * 64,
                           DATABASE_URL=f'postgresql://user:password@{host}/app{query}')
                result = subprocess.check_output(
                    [sys.executable, '-c',
                     'import json; from config.settings import DATABASES; '
                     'print(json.dumps(DATABASES["default"].get("OPTIONS", {}).get("sslmode")))'],
                    cwd=Path(__file__).resolve().parents[1], env=env, text=True,
                )
                self.assertEqual(json.loads(result), expected)
