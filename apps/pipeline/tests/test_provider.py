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
    def test_recorded_asr_uses_plural_language_and_a_safe_filename(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "private-source-name.mp3"
            audio.write_bytes(b"audio-content")
            with patch.object(provider, "request", return_value=b'{"text":"Evidence"}') as request:
                self.assertEqual(provider.transcribe_audio(audio)["text"], "Evidence")
                path, body, mime = request.call_args.args
                self.assertEqual(path, "audio/transcriptions")
                self.assertIn(b'name="languages[]"', body)
                self.assertNotIn(b'name="language"', body)
                self.assertNotIn(b"private-source-name", body)
                self.assertIn("multipart/form-data; boundary=", mime)
            with patch.object(provider, "request", return_value=b'{"text":""}'):
                self.assertRaises(RuntimeError, provider.transcribe_audio, audio)

    def test_structured_output_rejects_incomplete_and_refused_responses(self):
        for response in [{"status": "incomplete", "output": []},
                         {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]}]:
            with patch.object(provider, "json_request", return_value=response):
                self.assertRaises(RuntimeError, provider.structured, "instructions", {}, {}, "test", "model")
        response = {"status": "completed", "output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": "{\"passed\":true}"}]}]}
        with patch.object(provider, "json_request", return_value=response) as request:
            self.assertEqual(provider.structured("instructions", {}, {}, "test", "model"), {"passed": True})
            self.assertFalse(request.call_args.args[1]["store"])
            self.assertEqual(request.call_args.args[1]["text"]["format"]["type"], "json_schema")

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
