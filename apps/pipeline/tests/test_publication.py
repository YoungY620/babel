"""Complete publication snapshots retain verified archives and localized RSS."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import build_publication
import tts
from quality_fixture import approve
from test_tts import test_audio

REPO = build_publication.REPO
DICT = json.loads((REPO / 'site/feed-dict.json').read_text())
SERIES = json.loads((REPO / 'site/series.json').read_text())
AUDIO = 'https://github.com/example/babel/releases/download/audio'
SITE = 'https://example.github.io/babel'


def completed(episodes, slug, date):
    directory = episodes / slug
    directory.mkdir(parents=True)
    # Missing show is the existing arbitrary-video path, grouped under localized Other audio.
    (directory / 'meta.json').write_text(json.dumps({'title': 'Test', 'slug': slug, 'pubDate': date}))
    approve(directory)
    rows = json.loads((directory / 'transcript_zh.json').read_text())
    with patch.object(tts, 'speech', return_value=test_audio()), patch.object(tts, 'verify_audio', return_value={'passed': True, 'issues': []}):
        tts.render(directory, rows, 'cedar')


class PublicationTests(unittest.TestCase):
    def test_rss_uses_only_localized_verified_items_and_discloses_ai(self):
        catalog = json.loads((REPO / 'apps/web/public/catalog.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_publication.render_feeds(root, catalog, SITE, DICT)
            self.assertEqual(ET.parse(root / 'feed.xml').findall('./channel/item'), [])
            self.assertEqual(ET.parse(root / 'feed-en.xml').find('./channel/title').text, 'Babel')
            self.assertRaises(ValueError, build_publication.render_feeds, root, catalog, SITE + '?secret=private', DICT)
            self.assertRaises(ValueError, build_publication.render_feeds, root, catalog, SITE, DICT, 'Babel', 'private@example.com')

    @unittest.skipUnless(shutil.which('pnpm') and shutil.which('ffmpeg'), 'Node and FFmpeg required')
    def test_archived_episodes_survive_source_cleanup_and_unchanged_snapshots_are_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episodes = root / 'episodes'
            completed(episodes, 'first', 'Fri, 16 Oct 2026 00:00:00 GMT')
            first = root / 'first-snapshot'
            before = build_publication.build_snapshot(first, episodes, SERIES, REPO / 'site', AUDIO, SITE, DICT)
            self.assertEqual([item['id'] for item in before['episodes']], ['first'])
            self.assertEqual(before['episodes'][0]['seriesId'], 'other')
            self.assertEqual([show['id'] for show in before['series']].count('other'), 1)
            shutil.rmtree(episodes / 'first')
            completed(episodes, 'second', 'Sat, 17 Oct 2026 00:00:00 GMT')
            combined = root / 'combined'
            catalog = build_publication.build_snapshot(combined, episodes, SERIES, REPO / 'site', AUDIO, SITE, DICT, previous=first)
            self.assertEqual([item['id'] for item in catalog['episodes']], ['second', 'first'])
            self.assertEqual((combined / 'episodes/first/detail.json').read_bytes(), (first / 'episodes/first/detail.json').read_bytes())
            self.assertFalse((episodes / 'first').exists())
            english = (combined / 'feed-en.xml').read_text()
            chinese = (combined / 'feed.xml').read_text()
            self.assertFalse(any('\u4e00' <= char <= '\u9fff' for char in english))
            self.assertIn('AI-generated narration', english)
            self.assertIn('测试节目', chinese)
            self.assertIn('AI 合成配音', chinese)
            for name in ['feed.xml', 'feed-en.xml']:
                items = ET.parse(combined / name).findall('./channel/item')
                self.assertEqual(len(items), 2)
                self.assertEqual(items[0].find('enclosure').attrib['url'], catalog['episodes'][0]['audio']['url'])
            stable = root / 'stable'
            rebuilt = build_publication.build_snapshot(stable, episodes, SERIES, REPO / 'site', AUDIO, SITE, DICT, previous=combined)
            self.assertEqual(rebuilt, catalog)
            self.assertEqual((stable / 'feed-en.xml').read_bytes(), (combined / 'feed-en.xml').read_bytes())
            broken = root / 'broken-previous'
            shutil.copytree(combined, broken)
            (broken / 'episodes/first/en.vtt').write_text('WEBVTT\n')
            rejected = root / 'rejected'
            self.assertRaises(subprocess.CalledProcessError, build_publication.build_snapshot,
                              rejected, episodes, SERIES, REPO / 'site', AUDIO, SITE, DICT, broken)
            self.assertFalse(rejected.exists())
            self.assertEqual((combined / 'episodes/first/en.vtt').read_bytes(), (first / 'episodes/first/en.vtt').read_bytes())
            self.assertFalse(list(combined.rglob('source.mp3')))
            self.assertFalse(list(combined.rglob('speech.json')))
            self.assertFalse(list(combined.rglob('config.env')))
            self.assertRaises(ValueError, build_publication.build_snapshot, combined, episodes, SERIES, REPO / 'site', AUDIO, SITE, DICT)

    @unittest.skipUnless(shutil.which('pnpm'), 'Node required')
    def test_invalid_previous_snapshot_never_creates_output_or_replaces_prior_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'new'
            # A valid reference remains a preview; it is never promoted into a production ledger.
            self.assertRaises(ValueError, build_publication.build_snapshot, target, root / 'episodes', SERIES,
                              REPO / 'site', AUDIO, SITE, DICT, REPO / 'apps/web/public')
            self.assertFalse(target.exists())
            self.assertTrue((REPO / 'apps/web/public/episodes/babel-preview/detail.json').exists())
