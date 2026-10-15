import io
import base64
import types
import wave
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import provider


class ProviderTests(unittest.TestCase):
    def test_realtime_audio_requires_completed_response_and_redacts_errors(self):
        pcm = b"\x01\x00" * 240
        events = [{"type": "session.created"}, {"type": "session.updated"},
                  {"type": "response.output_audio.delta", "delta": base64.b64encode(pcm).decode()},
                  {"type": "response.done", "response": {"status": "completed"}}]
        socket = Mock()
        connector = Mock(return_value=socket)
        module = types.SimpleNamespace(create_connection=connector, WebSocketException=ConnectionError)
        with patch.dict(sys.modules, {"websocket": module}), \
                patch.dict(os.environ, {"OPENAI_API_KEY": "sensitive-value"}):
            socket.recv.side_effect = [json.dumps(event) for event in events]
            result = provider.speech("准确朗读。", "cedar", "gpt-realtime-2.1", "Read verbatim")
            with wave.open(io.BytesIO(result)) as wav:
                self.assertEqual(wav.getframerate(), 24000)
                self.assertEqual(wav.readframes(240), pcm)
            sent = [json.loads(call.args[0]) for call in socket.send.call_args_list]
            self.assertEqual([e["type"] for e in sent],
                             ["session.update", "conversation.item.create", "response.create"])
            self.assertEqual(sent[0]["session"]["audio"]["output"]["voice"], "cedar")
            for event in [{"type": "response.done", "response": {"status": "incomplete"}},
                          {"type": "error", "error": {"message": "sensitive-value"}}]:
                socket.recv.side_effect = [json.dumps(event)]
                with self.assertRaises(RuntimeError) as caught:
                    provider.speech("准确朗读。", "cedar", "gpt-realtime-2.1", "Read verbatim")
                self.assertNotIn("sensitive-value", str(caught.exception))
            self.assertEqual(socket.close.call_count, 3)

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
