import { z } from 'zod';

export const locales = ['zh-CN', 'en'] as const;
export type Locale = typeof locales[number];
const text = z.string().trim().min(1).max(100_000);
export const localized = z.strictObject({ 'zh-CN': text, en: text });
const id = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/).max(160);
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const seconds = z.number().finite().nonnegative();
const https = z.url().refine(value => {
  const url = new URL(value);
  return url.protocol === 'https:' && !url.username && !url.password;
}, 'Public HTTPS URL required');
const cover = z.string().regex(/^covers\/[a-z0-9-]+\.(?:svg|png|jpg|webp)$/);
const detailPath = z.string().regex(/^episodes\/[a-z0-9-]+\/detail\.json$/);
const captionPath = z.string().regex(/^episodes\/[a-z0-9-]+\/(?:zh-CN|en)\.vtt$/);
const quality = z.discriminatedUnion('kind', [
  z.strictObject({ kind: z.literal('verified-podcast'), model: text, reviewModel: text,
    reviewedUnits: z.number().int().positive() }),
  z.strictObject({ kind: z.literal('reference-preview'), model: text, voice: text,
    method: z.literal('reference-asr'), characterErrorRate: z.number().min(0).max(1) }),
]);
export const episodeSchema = z.strictObject({
  id, seriesId: id, title: localized, summary: localized,
  publishedAt: z.iso.datetime(), sourceUrl: https.optional(), cover,
  audio: z.strictObject({ url: https, sha256: sha, bytes: z.number().int().positive(),
    durationSeconds: seconds.positive(), language: z.literal('zh-CN'), synthetic: z.literal(true) }),
  quality, detail: detailPath,
  captions: z.strictObject({ 'zh-CN': captionPath, en: captionPath }),
});
export const seriesSchema = z.strictObject({
  id, title: localized, summary: localized, cover,
  links: z.array(z.strictObject({ label: localized, url: https })).max(10),
});
export const catalogSchema = z.strictObject({
  schemaVersion: z.literal(1), generatedAt: z.iso.datetime(),
  series: z.array(seriesSchema), episodes: z.array(episodeSchema),
}).superRefine((catalog, ctx) => {
  for (const field of ['series', 'episodes'] as const) {
    if (new Set(catalog[field].map(item => item.id)).size !== catalog[field].length)
      ctx.addIssue({ code: 'custom', path: [field], message: 'Duplicate IDs' });
  }
  const series = new Set(catalog.series.map(item => item.id));
  for (const [i, episode] of catalog.episodes.entries()) {
    if (!series.has(episode.seriesId))
      ctx.addIssue({ code: 'custom', path: ['episodes', i, 'seriesId'], message: 'Unknown series' });
    if (episode.detail !== `episodes/${episode.id}/detail.json` ||
        locales.some(locale => episode.captions[locale] !== `episodes/${episode.id}/${locale}.vtt`))
      ctx.addIssue({ code: 'custom', path: ['episodes', i], message: 'Episode paths must match its ID' });
  }
});
export const detailSchema = z.strictObject({
  schemaVersion: z.literal(1), episodeId: id,
  article: localized,
  cues: z.array(z.strictObject({ start: seconds, end: seconds.positive(), speaker: text, text: localized })),
}).superRefine((detail, ctx) => {
  let end = 0;
  detail.cues.forEach((cue, i) => {
    if (cue.start < end || cue.end <= cue.start)
      ctx.addIssue({ code: 'custom', path: ['cues', i], message: 'Invalid generated-audio timeline' });
    end = cue.end;
  });
});
export type Catalog = z.infer<typeof catalogSchema>;
export type Episode = z.infer<typeof episodeSchema>;
export type EpisodeDetail = z.infer<typeof detailSchema>;

export function renderVtt(cues: EpisodeDetail['cues'], locale: Locale): string {
  const timestamp = (seconds: number) => {
    const ms = Math.round(seconds * 1000);
    return `${String(Math.floor(ms / 3_600_000)).padStart(2, '0')}:${String(Math.floor(ms / 60_000) % 60).padStart(2, '0')}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
  };
  const escape = (text: string) => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replace(/[\r\n]/g, ' ');
  return 'WEBVTT\n\n' + cues.map(cue => `${timestamp(cue.start)} --> ${timestamp(cue.end)}\n${escape(cue.text[locale])}`).join('\n\n') + '\n';
}
