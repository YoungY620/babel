import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, writeFile, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { catalogSchema, detailSchema, renderVtt } from '../src/index.ts';
import { validateDirectory } from '../src/validate.ts';

const label = { 'zh-CN': '试听', en: 'Preview' };
const episode = {
  id: 'preview', seriesId: 'babel', title: label, summary: label,
  publishedAt: '2026-10-16T00:00:00Z', cover: 'covers/babel.svg',
  audio: { url: 'https://github.com/example/babel/releases/download/audio/preview.mp3',
    sha256: 'a'.repeat(64), bytes: 2000, durationSeconds: 20, language: 'zh-CN', synthetic: true },
  quality: { kind: 'reference-preview', model: 'reference', voice: 'preset',
    method: 'reference-asr', characterErrorRate: 0.01 },
  detail: 'episodes/preview/detail.json',
  captions: { 'zh-CN': 'episodes/preview/zh-CN.vtt', en: 'episodes/preview/en.vtt' },
};
const catalog = { schemaVersion: 1, generatedAt: '2026-10-16T00:00:00Z',
  series: [{ id: 'babel', title: label, summary: label, cover: 'covers/babel.svg', links: [] }],
  episodes: [episode] };
const detail = { schemaVersion: 1, episodeId: 'preview', article: label,
  cues: [{ start: 0, end: 19, speaker: 'Narrator', text: label }] };

test('requires complete bilingual data, provenance, safe URLs and referential integrity', () => {
  assert.ok(catalogSchema.safeParse(catalog).success);
  for (const invalid of [
    { ...catalog, episodes: [{ ...episode, title: { en: 'Preview' } }] },
    { ...catalog, episodes: [{ ...episode, audio: { ...episode.audio, url: 'javascript:alert(1)' } }] },
    { ...catalog, episodes: [{ ...episode, quality: { kind: 'verified-podcast', model: 'x' } }] },
    { ...catalog, episodes: [{ ...episode, detail: 'episodes/other/detail.json' }] },
    { ...catalog, episodes: [{ ...episode, seriesId: 'missing' }] },
    { ...catalog, episodes: [{ ...episode, sourceUrl: 'https://example.com/feed?token=private' }] },
    { ...catalog, episodes: [episode, episode] },
  ]) assert.equal(catalogSchema.safeParse(invalid).success, false);
  assert.equal(detailSchema.safeParse({ ...detail, cues: [detail.cues[0], detail.cues[0]] }).success, false);
});

test('validates actual detail, captions and assets without following escaping symlinks', async () => {
  const root = await mkdtemp(join(tmpdir(), 'babel-catalog-'));
  const outside = await mkdtemp(join(tmpdir(), 'babel-outside-'));
  try {
    await mkdir(join(root, 'covers'));
    await mkdir(join(root, 'episodes/preview'), { recursive: true });
    await writeFile(join(root, 'catalog.json'), JSON.stringify(catalog));
    await writeFile(join(root, 'covers/babel.svg'), '<svg/>');
    await writeFile(join(root, episode.detail), JSON.stringify(detail));
    for (const locale of ['zh-CN', 'en'] as const) await writeFile(join(root, episode.captions[locale]), renderVtt(detail.cues, locale));
    await validateDirectory(root);
    await writeFile(join(root, episode.captions.en), 'WEBVTT\n');
    await assert.rejects(validateDirectory(root), /Captions do not match/);
    await writeFile(join(root, episode.captions.en), renderVtt(detail.cues, 'en'));
    await writeFile(join(root, episode.detail), JSON.stringify({ ...detail, episodeId: 'wrong' }));
    await assert.rejects(validateDirectory(root), /does not match/);
    await writeFile(join(root, episode.detail), JSON.stringify({ ...detail,
      cues: [{ ...detail.cues[0], end: 25 }] }));
    await assert.rejects(validateDirectory(root), /does not match/);
    await writeFile(join(root, episode.detail), JSON.stringify(detail));
    await writeFile(join(outside, 'cover.svg'), '<svg/>');
    await rm(join(root, 'covers/babel.svg'));
    await symlink(join(outside, 'cover.svg'), join(root, 'covers/babel.svg'));
    await assert.rejects(validateDirectory(root), /escapes/);
  } finally {
    await rm(root, { recursive: true, force: true });
    await rm(outside, { recursive: true, force: true });
  }
});
