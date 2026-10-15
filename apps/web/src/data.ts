import {
  catalogSchema,
  detailSchema,
  type Episode,
  type EpisodeDetail,
} from "@babel/catalog";
export const assetUrl = (path: string) => `${import.meta.env.BASE_URL}${path}`;
async function load(path: string, signal: AbortSignal) {
  const response = await fetch(assetUrl(path), { signal });
  if (!response.ok) throw new Error("Could not load public data");
  return response.json();
}
export async function loadCatalog(signal: AbortSignal) {
  return catalogSchema.parse(await load("catalog.json", signal));
}
export async function loadDetail(
  episode: Episode,
  signal: AbortSignal,
): Promise<EpisodeDetail> {
  const detail = detailSchema.parse(await load(episode.detail, signal));
  if (
    detail.episodeId !== episode.id ||
    !detail.cues.length ||
    detail.cues.at(-1)!.end > episode.audio.durationSeconds + 0.1
  )
    throw new Error("Detail does not match audio");
  return detail;
}
export function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return value >= 3600
    ? `${Math.floor(value / 3600)}:${String(Math.floor(value / 60) % 60).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`
    : `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}
