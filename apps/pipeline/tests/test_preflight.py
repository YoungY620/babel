"""Provider preflight: fail fast on invalid credentials, never leak key material."""
import io
import os
import runpy
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import preflight


class PreflightTests(unittest.TestCase):
    def test_http_200_passes(self):
        with patch.object(preflight.provider, "request", return_value=b'{"data":[]}'):
            self.assertTrue(preflight.check_provider())

    def test_cli_exit_codes(self):
        with patch.object(preflight.provider, "request", return_value=b"{}"), \
                redirect_stdout(io.StringIO()):
            runpy.run_path(str(Path(preflight.__file__)), run_name="__main__")
        with patch.object(preflight.provider, "request",
                          side_effect=RuntimeError("Model provider returned HTTP 401 (invalid_api_key) for models")), \
                redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                runpy.run_path(str(Path(preflight.__file__)), run_name="__main__")

    def test_401_aborts_with_status_but_no_key_material(self):
        secret = "example-sensitive-value"
        with patch.dict(os.environ, {"OPENAI_API_KEY": secret}), \
                patch.object(preflight.provider, "request",
                             side_effect=RuntimeError(
                                 "Model provider returned HTTP 401 (invalid_api_key) for models")):
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
                preflight.check_provider()
            self.assertEqual(caught.exception.code, 1)
            self.assertIn("401", stderr.getvalue())
            self.assertIn("aborting before heavy work", stderr.getvalue())
            self.assertNotIn(secret, stderr.getvalue())

    def test_network_error_aborts_fail_closed(self):
        with patch.object(preflight.provider, "request",
                          side_effect=RuntimeError("Model provider connection failed for models")):
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit):
                preflight.check_provider()
            self.assertIn("connection failed", stderr.getvalue())

    def test_missing_key_aborts_fail_closed(self):
        env = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit):
                preflight.check_provider()
            self.assertIn("OPENAI_API_KEY is not set", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
