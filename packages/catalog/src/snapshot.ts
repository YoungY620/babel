import { copyFile, mkdir, readFile, realpath } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { catalogSchema, locales } from './index.ts';
import { safeFile, validateDirectory } from './validate.ts';

/** Read only typed data from a snapshot. Covers come from reviewed code assets. */
export async function copySnapshot(input: string, output: string, assets: string) {
  const root = await realpath(input);
  const owned = await realpath(assets);
  const catalog = catalogSchema.parse(JSON.parse(await readFile(await safeFile(root, 'catalog.json'), 'utf8')));
  await mkdir(output); // A fresh directory prevents stale or attacker-supplied output files.
  const copy = async (source: string, path: string) => {
    const file = await safeFile(source, path);
    const target = resolve(output, path);
    await mkdir(dirname(target), { recursive: true });
    await copyFile(file, target);
  };
  await copy(root, 'catalog.json');
  for (const episode of catalog.episodes) {
    await copy(root, episode.detail);
    for (const locale of locales) await copy(root, episode.captions[locale]);
  }
  const covers = new Set([...catalog.series.map(series => series.cover), ...catalog.episodes.map(episode => episode.cover)]);
  for (const cover of covers) await copy(owned, cover);
  await validateDirectory(output);
  return catalog;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [input, output, assets] = process.argv.slice(2);
  if (!input || !output || !assets) throw new Error('Usage: snapshot INPUT FRESH_OUTPUT REVIEWED_ASSETS');
  await copySnapshot(input, output, assets);
  console.log('Typed publication snapshot copied');
}
