"""A single CPU worker must retain completed chunks across interruptions."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'transcribe', Path(__file__).parents[1] / 'pipeline/transcribe.py')
transcribe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transcribe)


class SerialExecutor:
    def __init__(self, **kwargs):
        assert kwargs['max_workers'] == 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def map(self, worker, todo):
        return map(worker, todo)


class CheckpointTest(unittest.TestCase):
    def test_single_worker_resumes_completed_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / 'episodes/long'
            parts = episode / '.transcribe_parts'
            parts.mkdir(parents=True)
            (episode / 'source.mp3').touch()
            for n in range(2):
                (parts / f'part{n:03d}.mp3').touch()
            cached = [{'start': 0, 'end': 1, 'text': 'first'}]
            (parts / 'part000.json').write_text(json.dumps(cached))
            mutagen = SimpleNamespace(File=lambda _: SimpleNamespace(
                info=SimpleNamespace(length=1800)))
            with (patch.object(transcribe, 'ROOT', root),
                  patch.dict(sys.modules, mutagen=mutagen),
                  patch.object(sys, 'argv', ['transcribe', 'long', '--jobs', '1']),
                  patch('concurrent.futures.ProcessPoolExecutor', SerialExecutor),
                  patch.object(transcribe, '_worker', side_effect=RuntimeError('stop'))):
                with self.assertRaises(RuntimeError):
                    transcribe.main()
                self.assertEqual(json.loads((parts / 'part000.json').read_text()), cached)
            remaining = [{'start': 1800, 'end': 1801, 'text': 'second'}]
            with (patch.object(transcribe, 'ROOT', root),
                  patch.dict(sys.modules, mutagen=mutagen),
                  patch.object(sys, 'argv', ['transcribe', 'long', '--jobs', '1']),
                  patch('concurrent.futures.ProcessPoolExecutor', SerialExecutor),
                  patch.object(transcribe, '_worker', return_value=remaining) as worker):
                transcribe.main()
                self.assertEqual(worker.call_count, 1)
                self.assertEqual(json.loads((episode / 'transcript_en.json').read_text()),
                                 cached + remaining)
                self.assertFalse(parts.exists())
