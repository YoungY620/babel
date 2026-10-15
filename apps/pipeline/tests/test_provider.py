import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import provider


class ProviderTests(unittest.TestCase):
    def test_credentials_are_redacted_and_exhausted_quota_is_not_retried(self):
        for status, code in [(401, "invalid_api_key"), (429, "insufficient_quota")]:
            with self.subTest(status=status):
                secret = "example-sensitive-value"
                error = urllib.error.HTTPError("https://api.openai.com/v1/models", status, "error", {},
                    io.BytesIO(json.dumps({"error": {"code": code, "message": secret}}).encode()))
                with patch.dict(os.environ, {"OPENAI_API_KEY": secret}), \
                        patch.object(provider.urllib.request, "urlopen", side_effect=error) as call:
                    with self.assertRaises(RuntimeError) as caught:
                        provider.json_request("models")
                    self.assertNotIn(secret, str(caught.exception))
                    self.assertIn(code, str(caught.exception))
                    self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
