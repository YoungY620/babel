# React Web validation

Scope: rebuild the static player as a bilingual React library. Keep series browsing, covers, basic information, RSS and text access; add search, local language preference, speed, seek and resume. The existing unverified trailer is excluded by the new catalog contract. The replacement preview is original reference audio with explicit qualifications, not a relabeled production podcast.

## Rendered checks

The real app was inspected through Computer Use in the in-app browser at 1440, 1728 and 390 CSS pixels. Chinese and English switch visible content, labels, dates, title and dialogs together. Desktop and mobile baseline screenshots were saved before development, followed by screenshots of the new library, sticky player and transcript.

Checked interactions:

- Actual GitHub Release audio playback, pause, repeated Play, speed and transcript seek.
- Reload retains English preference, 1.5× speed and a 16.9-second playback position.
- Quick pause before metadata loads does not overwrite saved progress.
- Search, no results, reset and series filtering.
- Transcript/article switch, Escape, focus return and actual WebVTT download.
- Subscribe dialog and successful address-copy feedback.
- Onest font loaded; no horizontal overflow; browser error log empty.

Spacing measurement completed with no critical or serious findings after expanding touch targets, using explicit accessible labels and correcting flexible gaps. Remaining moderate values come from native controls and responsive/automatic spacing. Visual review checked the screenshots separately. Copy comprehension passed after removing repeated introduction text and shortening the preview explanation; full qualification remains in the transcript dialog.

## Automated checks

Moon runs TypeScript, dictionary coverage/pluralization, shared data validation, Python regressions and the production build. Initial JavaScript is approximately 118 kB gzipped; transcript and article code loads separately. Fonts are bundled locally.

Pages deployment is a separate reviewed change. This validation does not claim a live cloud voice test or a measured full-pipeline capacity.
