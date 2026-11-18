import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class DatabaseSSLSettingsTests(unittest.TestCase):
    def test_https_defaults_and_environment_overrides(self):
        names = ('SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'SECURE_SSL_REDIRECT')
        cases = [
            ({'DEBUG': 'False'}, [True, True, True, 'None']),
            ({'DEBUG': 'True'}, [False, False, False, 'Lax']),
            ({'DEBUG': 'False', **dict.fromkeys(names, 'False')}, [False, False, False, 'Lax']),
            ({'DEBUG': 'False', 'SESSION_COOKIE_SECURE': '0', 'CSRF_COOKIE_SECURE': 'TRUE',
              'SECURE_SSL_REDIRECT': '1'}, [False, True, True, 'None']),
            ({'DEBUG': 'True', **dict.fromkeys(names, 'True')}, [True, True, True, 'Lax']),
        ]
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                env = dict(os.environ, SECRET_KEY='x' * 64,
                           DATABASE_URL='postgresql://user:password@db/app')
                for name in names:
                    env.pop(name, None)
                env.update(overrides)
                # Defaults must not depend on a developer's ignored .env files.
                code = (
                    'import json; from unittest.mock import patch\n'
                    'with patch("pathlib.Path.read_text", return_value=""):\n'
                    ' import config.settings as s\n'
                    ' print(json.dumps([s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, '
                    's.SECURE_SSL_REDIRECT, s.CSRF_COOKIE_SAMESITE]))\n'
                )
                result = subprocess.check_output(
                    [sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                    env=env, text=True,
                )
                self.assertEqual(json.loads(result), expected)

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
