import { readFile, realpath } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { catalogSchema, detailSchema, locales, renderVtt } from './index.ts';

export async function validateDirectory(directory: string) {
  const root = await realpath(directory);
  const load = async (path: string) => {
    const file = await realpath(resolve(root, path));
    if (!file.startsWith(root + sep)) throw new Error('Asset escapes publication directory');
    return readFile(file, 'utf8');
  };
  const catalog = catalogSchema.parse(JSON.parse(await load('catalog.json')));
  for (const series of catalog.series) await load(series.cover);
  for (const episode of catalog.episodes) {
    await load(episode.cover);
    const detail = detailSchema.parse(JSON.parse(await load(episode.detail)));
    if (detail.episodeId !== episode.id || !detail.cues.length ||
        detail.cues.at(-1)!.end > episode.audio.durationSeconds + 0.1)
      throw new Error('Episode detail does not match audio');
    for (const locale of locales) {
      const vtt = await load(episode.captions[locale]);
      if (vtt !== renderVtt(detail.cues, locale)) throw new Error('Captions do not match generated timeline and text');
    }
  }
  return catalog;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await validateDirectory(process.argv[2] ?? '../../apps/pipeline/docs');
  console.log('Catalog and publication assets verified');
}
