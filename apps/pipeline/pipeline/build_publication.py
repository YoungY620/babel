#!/usr/bin/env python3
"""Build one complete typed Web/RSS snapshot without uploading or changing a ledger."""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlsplit

from build_catalog import REPO, ROOT, export_catalog, write_json
from paths import data_root

ITUNES = 'http://www.itunes.com/dtds/podcast-1.0.dtd'
ATOM = 'http://www.w3.org/2005/Atom'
ET.register_namespace('itunes', ITUNES)
ET.register_namespace('atom', ATOM)


def typed_copy(source, output, assets):
    subprocess.run(['pnpm', '--filter', '@babel/catalog', 'snapshot', str(source.resolve()),
                    str(output.resolve()), str(assets.resolve())], cwd=REPO, check=True, capture_output=True, text=True)
    return json.loads((output / 'catalog.json').read_text())


def render_feeds(directory, catalog, site_url, dictionary, author='Babel', email=None):
    base = urlsplit(site_url)
    if (base.scheme != 'https' or not base.hostname or base.username or base.password or base.query or base.fragment):
        raise ValueError('Canonical HTTPS site URL required')
    if email and not re.fullmatch(r'[A-Za-z0-9_.+\-]+@users\.noreply\.github\.com', email):
        raise ValueError('Only public noreply owner email is permitted')
    site_url = site_url.rstrip('/')
    for locale, name in [('zh-CN', 'feed.xml'), ('en', 'feed-en.xml')]:
        text = dictionary[locale]
        rss = ET.Element('rss', {'version': '2.0'})
        channel = ET.SubElement(rss, 'channel')
        def tag(parent, key, value):
            ET.SubElement(parent, key).text = str(value)
        tag(channel, 'title', text['title'])
        tag(channel, 'link', site_url + '/')
        tag(channel, 'description', text['description'])
        tag(channel, 'language', 'zh-CN')  # The spoken audio remains Mandarin in both metadata feeds.
        tag(channel, 'lastBuildDate', format_datetime(datetime.fromisoformat(catalog['generatedAt']), usegmt=True))
        ET.SubElement(channel, f'{{{ATOM}}}link', {'href': site_url + '/' + name, 'rel': 'self', 'type': 'application/rss+xml'})
        tag(channel, f'{{{ITUNES}}}author', author)
        tag(channel, f'{{{ITUNES}}}explicit', 'false')
        if email:
            owner = ET.SubElement(channel, f'{{{ITUNES}}}owner')
            tag(owner, f'{{{ITUNES}}}name', author)
            tag(owner, f'{{{ITUNES}}}email', email)
        for episode in catalog['episodes']:
            if episode['quality']['kind'] != 'verified-podcast':
                continue
            item = ET.SubElement(channel, 'item')
            tag(item, 'title', episode['title'][locale])
            description = text['aiDisclosure'] + ' ' + episode['summary'][locale]
            tag(item, 'description', description)
            tag(item, f'{{{ITUNES}}}summary', description)
            tag(item, 'link', site_url + '/')
            tag(item, 'pubDate', format_datetime(datetime.fromisoformat(episode['publishedAt']), usegmt=True))
            ET.SubElement(item, 'guid', {'isPermaLink': 'false'}).text = episode['id'] + '-zh-' + episode['audio']['sha256']
            ET.SubElement(item, 'enclosure', {'url': episode['audio']['url'], 'length': str(episode['audio']['bytes']), 'type': 'audio/mpeg'})
            ET.SubElement(item, f'{{{ITUNES}}}image', {'href': site_url + '/' + episode['cover']})
            tag(item, f'{{{ITUNES}}}author', author)
            tag(item, f'{{{ITUNES}}}duration', int(episode['audio']['durationSeconds']))
        ET.indent(rss)
        ET.ElementTree(rss).write(directory / name, encoding='utf-8', xml_declaration=True)


def build_snapshot(output, episodes, series, assets, audio_base, site_url, dictionary, previous=None, author='Babel', email=None):
    if output.exists():
        raise ValueError('Publication output must be a fresh directory')
    # Validation/copy happens in private staging. A failed snapshot never replaces prior output.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.publication-') as tmp:
        stage = Path(tmp)
        old = None
        if previous is not None:
            old = typed_copy(previous, stage / 'old', assets)
            if any(episode['quality']['kind'] != 'verified-podcast' for episode in old['episodes']):
                raise ValueError('A production ledger cannot contain reference previews')
        fresh = export_catalog(stage / 'fresh', episodes, series, assets, audio_base)
        return _merge_snapshot(output, stage, old, fresh, assets, site_url, dictionary, author, email)


def _merge_snapshot(output, stage, old, fresh, assets, site_url, dictionary, author, email):
    shows = {show['id']: show for show in fresh['series']}
    entries = {}
    if old:
        for show in old['series']:
            shows.setdefault(show['id'], show)
        entries.update({episode['id']: (episode, stage / 'old') for episode in old['episodes']})
    entries.update({episode['id']: (episode, stage / 'fresh') for episode in fresh['episodes']})
    content = {'series': list(shows.values()),
               'episodes': sorted((pair[0] for pair in entries.values()), key=lambda episode: (episode['publishedAt'], episode['id']), reverse=True)}
    date = old['generatedAt'] if old and all(content[key] == old[key] for key in content) else fresh['generatedAt']
    catalog = {'schemaVersion': 1, 'generatedAt': date, **content}
    merged = stage / 'merged'
    write_json(merged / 'catalog.json', catalog)
    for episode, source in entries.values():
        for path in [episode['detail'], *episode['captions'].values()]:
            target = merged / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / path, target)
    typed_copy(merged, stage / 'complete', assets)
    render_feeds(stage / 'complete', catalog, site_url, dictionary, author, email)
    (stage / 'complete').rename(output)
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--site-url', required=True)
    parser.add_argument('--audio-base', required=True)
    parser.add_argument('--author', default='Babel')
    parser.add_argument('--email')
    args = parser.parse_args()
    series = json.loads((REPO / 'site/series.json').read_text())
    dictionary = json.loads((REPO / 'site/feed-dict.json').read_text())
    build_snapshot(args.output, data_root(ROOT) / 'episodes', series, REPO / 'site', args.audio_base, args.site_url,
                   dictionary, args.previous, args.author, args.email)


if __name__ == '__main__':
    main()
