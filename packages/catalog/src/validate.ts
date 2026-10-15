import { lstat, readFile, realpath } from 'node:fs/promises';
import { join, relative, resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { catalogSchema, detailSchema, locales, renderVtt } from './index.ts';

export async function safeFile(root: string, path: string) {
  const file = resolve(root, path);
  if (!file.startsWith(root + sep)) throw new Error('Asset escapes publication directory');
  let current = root;
  for (const part of relative(root, file).split(sep)) {
    current = join(current, part);
    if ((await lstat(current)).isSymbolicLink()) throw new Error('Symbolic links are not publication files; asset may escape');
  }
  if (!(await lstat(file)).isFile()) throw new Error('Publication asset must be a regular file');
  return file;
}

export async function validateDirectory(directory: string) {
  const root = await realpath(directory);
  const load = async (path: string) => {
    return readFile(await safeFile(root, path), 'utf8');
  };
  const catalog = catalogSchema.parse(JSON.parse(await load('catalog.json')));
  for (const series of catalog.series) await safeFile(root, series.cover);
  for (const episode of catalog.episodes) {
    await safeFile(root, episode.cover);
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
