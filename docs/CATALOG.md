# Web data contract v1

`packages/catalog/src/index.ts` defines the runtime schemas and inferred TypeScript types. The pipeline and Web client share this contract. Unknown properties, missing translations, duplicate IDs, unknown series, unsafe URLs and invalid audio timelines fail validation.

- `catalog.json`: bilingual series and episode metadata, covers, audio URLs, hashes, byte counts, generated duration, quality provenance and detail/caption paths.
- `episodes/<id>/detail.json`: bilingual article and timed bilingual cues. Cue times refer to the generated Chinese audio, never the source recording. English cues preserve source words; long source segments split across speech units are grouped once.
- `episodes/<id>/zh-CN.vtt` and `en.vtt`: WebVTT subtitles on that same generated clock.
- `covers/*`: public cover assets. Internal paths are relative and restricted. Directory validation rejects symlinks escaping the output root.

All localized fields require `zh-CN` and `en`. UI dictionaries remain separate from this content. Proper names can be the same in both locales. The audio language is explicitly Chinese; switching the interface does not imply an English audio track.

## Production export

The reviewed metadata stage writes `web.json` with bilingual `title`, `summary` and `article` objects, plus `transcriptSha256` containing the SHA-256 of the exact reviewed `transcript_zh.json` bytes. A changed transcript invalidates that review. `web-review.json` binds all exported content to that review. `completion.py` requires source-grounded text, metadata and speech verification together. Only episodes passing the speech completion and SHA-256 checks are exported. Legacy MP3 files and missing/stale bilingual metadata are excluded. Optional `sourceUrl` must be an explicitly reviewed canonical public URL; raw source/feed URLs are never copied. URLs reject query strings and fragments, except the standard YouTube watch URL with exactly one valid video ID. Publication dates without a known timezone use UTC, consistently on every host.

```sh
pnpm moon run pipeline:catalog -- --output /tmp/babel-public --audio-base https://github.com/OWNER/REPO/releases/download/audio
pnpm moon run catalog:validate -- /tmp/babel-public
```

The output directory must be empty. Build in staging, validate the complete directory, then publish the resulting snapshot. Export copies only the public allowlist; source recordings, speaker samples, caches and credentials stay private. This PR adds export tooling; it does not replace the existing Pages workflow yet.

`quality.kind = verified-podcast` requires the synthesis/audio review models, source and transcript SHA-256 values, and the transcription/text/review model provenance. Titles and summaries have short display limits; complete bilingual articles allow up to two million characters per language. A separately identified `reference-preview` may document an original voice sample with its actual reference-ASR result. Such a preview is not a completed podcast or evidence of full-pipeline capacity. Every audio item declares `synthetic: true`; clients and RSS must disclose AI-generated speech.

Validation checks structure and asset relationships. It does not replace acoustic listening, source-fidelity review or the speech pipeline's file hash gate.
