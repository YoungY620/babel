"""A single CPU worker must retain completed chunks across interruptions."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
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
    def setUp(self):
        # Server workflow tests must never read or remove production episode data.
        clean = {key: value for key, value in os.environ.items() if key not in {"BABEL_DATA_DIR", "RAW_ASR_MODEL"}}
        environment = patch.dict(os.environ, clean, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_single_worker_resumes_completed_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / '.data/episodes/long'
            parts = episode / '.transcribe_parts'
            parts.mkdir(parents=True)
            (episode / 'source.mp3').touch()
            for n in range(2):
                (parts / f'part{n:03d}.mp3').touch()
            transcribe.save(parts / 'plan.json', transcribe.source_plan(episode))
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

    def test_interrupted_split_does_not_expose_partial_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / '.data/episodes/long'
            episode.mkdir(parents=True)
            (episode / 'source.mp3').touch()
            mutagen = SimpleNamespace(File=lambda _: SimpleNamespace(
                info=SimpleNamespace(length=1800)))

            def interrupted(command, **kwargs):
                Path(command[-1].replace('%03d', '000')).touch()
                raise RuntimeError('interrupted split')

            with (patch.object(transcribe, 'ROOT', root),
                  patch.dict(sys.modules, mutagen=mutagen),
                  patch.object(sys, 'argv', ['transcribe', 'long', '--jobs', '1']),
                  patch.object(transcribe.subprocess, 'run', side_effect=interrupted)):
                with self.assertRaises(RuntimeError):
                    transcribe.main()
                self.assertFalse((episode / '.transcribe_parts').exists())
                self.assertFalse(list(episode.glob('.transcribe_split-*')))

    def test_source_model_and_raw_content_invalidate_cache_but_speaker_tags_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory / 'source.mp3'
            source.write_bytes(b'first recording')
            rows = [{'start': 0, 'end': 1, 'text': 'first'}]
            transcribe.save(directory / 'transcript_en.json', rows)
            transcribe.save(directory / 'transcribe.json', {
                'plan': transcribe.source_plan(directory), 'rawSha256': transcribe.raw_digest(rows)})
            self.assertTrue(transcribe.is_current(directory))
            rows[0]['speaker'] = 'SPEAKER_00'
            transcribe.save(directory / 'transcript_en.json', rows)
            self.assertTrue(transcribe.is_current(directory))
            self.assertFalse(transcribe.is_current(directory, 'other-model'))
            transcribe.save(directory / 'transcribe.json', {
                'plan': transcribe.source_plan(directory, 'custom-model'), 'rawSha256': transcribe.raw_digest(rows)})
            self.assertTrue(transcribe.is_current(directory))
            self.assertTrue(transcribe.is_current(directory, 'custom-model'))
            with patch.dict('os.environ', {'RAW_ASR_MODEL': 'changed-model'}):
                self.assertFalse(transcribe.is_current(directory))
            source.write_bytes(b'other recording')
            self.assertFalse(transcribe.is_current(directory))
            source.write_bytes(b'first recording')
            rows[0]['text'] = 'changed'
            transcribe.save(directory / 'transcript_en.json', rows)
            self.assertFalse(transcribe.is_current(directory))

    def test_path_escape_is_rejected_before_removing_artifacts(self):
        from paths import episode_directory
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / 'outside'
            outside.mkdir()
            (root / 'episodes').mkdir()
            (root / 'episodes/link').symlink_to(outside, target_is_directory=True)
            for slug in ['../outside', '.', 'link']:
                self.assertRaises(ValueError, episode_directory, root, slug)
