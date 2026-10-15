# Babel Web

Vite + React 19 client. GitHub Pages serves the build; no Node daemon is required.

```sh
pnpm install --frozen-lockfile
pnpm moon run web:dev
pnpm moon run web:check web:test web:build
pnpm --filter @babel/catalog validate apps/web/public
```

Open `http://127.0.0.1:5173/babel/`. Build output is `apps/web/dist`.

- UI messages are keys in components, mapped in `src/i18n/dict/zh-CN.json` and `en.json` through i18next. Language, document title, accessibility labels, dates, durations and dialogs switch together. Language and playback preferences persist locally; blocked storage does not prevent use.
- Series, covers, metadata and search use the shared catalog contract. Details load only when requested. Markdown is rendered without raw HTML execution.
- Audio uses native media events for actual playback state. Progress is keyed by episode ID and audio SHA, saved on pause/close and every five seconds. Metadata must load before saved progress can be replaced. Speed, seek and transcript jumps share the same media element.
- Native dialogs support keyboard focus, Escape and focus restoration. The sticky player reserves its measured height, including on mobile.
- All audio is explicitly marked synthetic. The included 19.6-second original CPU preview has reference-ASR provenance; it is not a complete podcast or a final cloud quality result. Unverified legacy audio is not included.
- `public/feed.xml` and `feed-en.xml` are initially empty feeds with localized metadata. Only fully verified podcasts belong in the subscription feed; previews remain separate.
- Optional public `VITE_SUPPORT_URL=https://ko-fi.com/<name>` adds the Ko-fi support link. Do not put credentials in any `VITE_*` value.

The current Pages workflow is replaced in a separate deployment PR. See `docs/CATALOG.md` for the pipeline export contract. Production media remains on GitHub Releases, outside the Git tree.
