"""Real process-tree termination and ordered, bounded admission."""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import budget
import convert
import fetch


class BudgetTests(unittest.TestCase):
    def test_timeout_kills_grandchildren_and_keeps_completed_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkpoint, leak = root / 'checkpoint', root / 'leak'
            checkpoint.write_text('approved work')
            grandchild = f'import time; from pathlib import Path; time.sleep(1); Path({str(leak)!r}).write_text("leaked")'
            parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{grandchild!r}]); time.sleep(20)'
            started = time.monotonic()
            with self.assertRaises(budget.BudgetExpired):
                budget.run_command([sys.executable, '-c', parent], deadline=time.time() + .2, capture=True)
            self.assertLess(time.monotonic() - started, 2)
            time.sleep(1)
            self.assertFalse(leak.exists())
            self.assertEqual(checkpoint.read_text(), 'approved work')

    def test_expired_budget_never_starts_a_process_and_exit_codes_propagate(self):
        with patch.object(budget.subprocess, 'Popen', side_effect=AssertionError('must not launch')):
            self.assertRaises(budget.BudgetExpired, budget.run_command, ['unused'], deadline=time.time() - 1)
        self.assertRaises(subprocess.CalledProcessError, budget.run_command,
                          [sys.executable, '-c', 'raise SystemExit(7)'], deadline=time.time() + 5)
        self.assertEqual(budget.run_command([sys.executable, '-c', 'print("ok")'],
                                          deadline=time.time() + 5, capture=True).stdout.strip(), 'ok')

    def test_parent_feed_or_network_work_is_also_interrupted(self):
        with self.assertRaises(budget.BudgetExpired), budget.work_deadline(time.time() + .05):
            time.sleep(2)

    def test_feeds_are_interleaved_without_fake_source_hour_or_count_caps(self):
        shows = [{'id': 'first', 'rss': 'https://example.com/first'}, {'id': 'second', 'rss': 'https://example.com/second'}]
        rows = [{'title': f'episode {index}', 'duration': '20:00:00'} for index in range(7)]
        with patch.object(convert, 'load_shows', return_value=shows), patch.object(convert, 'load_items', return_value=rows), patch.object(convert, 'is_done', return_value=False):
            targets = list(convert.cycle_targets())
        self.assertEqual(len(targets), 14)
        self.assertEqual([(show['id'], index) for show, index in targets[:4]], [('first', 0), ('second', 0), ('first', 1), ('second', 1)])

    def test_killed_or_failed_download_never_commits_partial_source(self):
        class Interrupted(io.BytesIO):
            def read(self, size=-1):
                if self.tell(): raise OSError('connection interrupted')
                return super().read(3)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'BABEL_DATA_DIR': tmp}):
            root = Path(tmp)
            item = {'title': 'Test', 'url': 'https://example.com/audio', 'bytes': 6}
            channel = {'title': 'Show', 'description': '', 'image': ''}
            show = {'id': 'test', 'rss': 'https://example.com/feed'}
            with patch.object(fetch, 'load_feed', return_value=(channel, [item])), patch.object(fetch.urllib.request, 'urlopen', return_value=Interrupted(b'abcdef')):
                self.assertRaises(OSError, fetch.download, show, 0)
            self.assertFalse((root / 'episodes/test/source.mp3').exists())
            self.assertFalse((root / 'episodes/test/meta.json').exists())
            truncated = io.BytesIO(b'short')
            truncated.headers = {'Content-Length': '100'}
            with patch.object(fetch, 'load_feed', return_value=(channel, [item])), patch.object(fetch.urllib.request, 'urlopen', return_value=truncated):
                self.assertRaises(OSError, fetch.download, show, 0)
            self.assertFalse((root / 'episodes/test/source.mp3').exists())
            with patch.object(fetch, 'load_feed', return_value=(channel, [item])), patch.object(fetch.urllib.request, 'urlopen', return_value=io.BytesIO(b'complete source')):
                fetch.download(show, 0)
            self.assertEqual((root / 'episodes/test/source.mp3').read_bytes(), b'complete source')

    def test_budget_control_cannot_be_swallowed_by_network_retry_handlers(self):
        with self.assertRaises(budget.BudgetExpired):
            with budget.work_deadline(time.time() + .05):
                try:
                    time.sleep(2)
                except (TimeoutError, Exception):
                    self.fail('Network retry swallowed cycle deadline')

    def test_cycle_downloads_only_the_episode_it_can_start(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'BABEL_DATA_DIR': tmp}):
            calls = []
            def download(*args):
                calls.append('download')
                return 'first'
            def process(slug):
                calls.append('process')
                raise budget.BudgetExpired('stopped')
            with patch.object(sys, 'argv', ['convert', '--cycle', '--publish-reserve-seconds', '0']), \
                    patch.object(convert, 'check_provider', return_value=True), \
                    patch.object(convert, 'cycle_targets', return_value=iter([({'id': 'show'}, 0), ({'id': 'show'}, 1)])), \
                    patch.object(convert, 'download_target', side_effect=download), \
                    patch.object(convert, 'process', side_effect=process):
                convert.main()
            self.assertEqual(calls, ['download', 'process'])
            self.assertNotIn('BABEL_PROCESS_DEADLINE', os.environ)

    def test_interrupted_video_encoder_never_commits_its_partial_mp3(self):
        import fetch_video
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'BABEL_DATA_DIR': tmp}):
            root = Path(tmp)
            result = root / 'result.json'
            info = {'title': 'Video', 'duration': 3}
            def interrupted(argv, **kwargs):
                if '--dump-json' in argv:
                    return subprocess.CompletedProcess(argv, 0, json.dumps(info))
                pending = Path(argv[argv.index('-o') + 1].replace('%(ext)s', 'mp3'))
                pending.write_bytes(b'partial encoder output')
                raise subprocess.CalledProcessError(1, argv)
            def successful(argv, **kwargs):
                if '--dump-json' in argv:
                    return subprocess.CompletedProcess(argv, 0, json.dumps(info))
                pending = Path(argv[argv.index('-o') + 1].replace('%(ext)s', 'mp3'))
                self.assertFalse(pending.exists())
                self.assertIn('bestaudio/best', argv)
                pending.write_bytes(b'complete source')
                return subprocess.CompletedProcess(argv, 0)
            with patch.object(sys, 'argv', ['fetch-video', 'https://example.com/video', '--result', str(result)]), \
                    patch.object(fetch_video.subprocess, 'run', side_effect=interrupted):
                self.assertRaises(subprocess.CalledProcessError, fetch_video.main)
            self.assertFalse((root / 'episodes/video/source.mp3').exists())
            with patch.object(sys, 'argv', ['fetch-video', 'https://example.com/video', '--result', str(result)]), \
                    patch.object(fetch_video.subprocess, 'run', side_effect=successful):
                fetch_video.main()
            self.assertEqual((root / 'episodes/video/source.mp3').read_bytes(), b'complete source')
            self.assertEqual(json.loads(result.read_text()), {'slug': 'video'})
