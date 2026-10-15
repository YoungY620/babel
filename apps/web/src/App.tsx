import {
  Component,
  Suspense,
  lazy,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { Search, X, Play, Rss, ArrowUpRight, FileText } from "lucide-react";
import type { Catalog, Episode, Locale } from "@babel/catalog";
import { assetUrl, loadCatalog } from "./data";
import { savePreference } from "./i18n";
import Player from "./Player";
const Subscribe = lazy(() =>
  import("./Dialogs").then((module) => ({ default: module.Subscribe })),
);
const Transcript = lazy(() =>
  import("./Dialogs").then((module) => ({ default: module.Transcript })),
);
class DialogBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

type Selection = { episode: Episode; request: number; startAt?: number };
export default function App() {
  const { t, i18n } = useTranslation();
  const locale: Locale = i18n.resolvedLanguage === "en" ? "en" : "zh-CN";
  const [catalog, setCatalog] = useState<Catalog>();
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState("");
  const [seriesFilter, setSeriesFilter] = useState("all");
  const [selection, setSelection] = useState<Selection>();
  const [dialog, setDialog] = useState<"subscribe" | Episode>();
  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = t("page.title");
    savePreference("babel-language", locale);
  }, [locale, t]);
  useEffect(() => {
    const controller = new AbortController();
    setError(false);
    void loadCatalog(controller.signal)
      .then(setCatalog)
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [reload]);
  const choose = (episode: Episode, startAt?: number) =>
    setSelection((previous) => ({
      episode,
      request: (previous?.request ?? 0) + 1,
      startAt,
    }));
  const support = import.meta.env.VITE_SUPPORT_URL;
  const supportUrl =
    typeof support === "string" &&
    /^https:\/\/ko-fi\.com\/[A-Za-z0-9_-]+\/?$/.test(support)
      ? support
      : undefined;
  const normalized = query.trim().toLocaleLowerCase(locale);
  const matches = (values: string[]) =>
    values.some((value) =>
      value.toLocaleLowerCase(locale).includes(normalized),
    );
  const groups =
    catalog?.series
      .filter((series) => seriesFilter === "all" || series.id === seriesFilter)
      .map((series) => {
        const all = catalog.episodes.filter(
          (episode) => episode.seriesId === series.id,
        );
        const seriesMatches = matches([
          ...Object.values(series.title),
          ...Object.values(series.summary),
        ]);
        const episodes = seriesMatches
          ? all
          : all.filter((episode) =>
              matches([
                ...Object.values(episode.title),
                ...Object.values(episode.summary),
              ]),
            );
        return {
          series,
          episodes,
          visible: seriesMatches || episodes.length > 0,
        };
      })
      .filter((group) => group.visible) ?? [];
  const date = (value: string) =>
    new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    }).format(new Date(value));
  const duration = (seconds: number) =>
    seconds < 60
      ? t("duration.seconds", { count: Math.round(seconds) })
      : t("duration.minutes", { count: Math.round(seconds / 60) });
  return (
    <>
      <a className="skip-link" href="#library">
        {t("skip.main")}
      </a>
      <header className="site-header">
        <a className="brand" href={import.meta.env.BASE_URL}>
          <img src={assetUrl("brand.svg")} alt="" />
          {t("brand")}
        </a>

        <div className="header-actions">
          <div
            className="segmented language-switch"
            role="group"
            aria-label={t("language.label")}
          >
            {(["zh-CN", "en"] as const).map((language) => (
              <button
                key={language}
                aria-pressed={locale === language}
                onClick={() => {
                  void i18n.changeLanguage(language);
                }}
              >
                {t(language === "en" ? "language.en" : "language.zh")}
              </button>
            ))}
          </div>
          <button
            className="primary subscribe-button"
            aria-label={t("subscribe")}
            onClick={() => setDialog("subscribe")}
          >
            <Rss size={18} />
            <span>{t("subscribe")}</span>
          </button>
        </div>
      </header>
      <main id="library">
        <section className="intro">
          <h1>{t("hero.title")}</h1>
        </section>
        <div className="browse-tools">
          <div className="search-field">
            <Search size={20} aria-hidden="true" />
            <input
              id="podcast-search"
              aria-label={t("search.label")}
              type="search"
              placeholder={t("search.placeholder")}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {query && (
              <button
                className="icon-button"
                onClick={() => setQuery("")}
                aria-label={t("search.clear")}
              >
                <X size={18} />
              </button>
            )}
          </div>
          <div className="filter">
            <select
              aria-label={t("filter.label")}
              value={seriesFilter}
              onChange={(event) => setSeriesFilter(event.target.value)}
            >
              <option value="all">{t("filter.all")}</option>
              {catalog?.series.map((series) => (
                <option key={series.id} value={series.id}>
                  {series.title[locale]}
                </option>
              ))}
            </select>
          </div>
        </div>
        {error ? (
          <div className="empty" role="alert">
            <p>{t("error.catalog")}</p>
            <button
              className="secondary"
              onClick={() => setReload((value) => value + 1)}
            >
              {t("error.retry")}
            </button>
          </div>
        ) : !catalog ? (
          <p role="status">{t("loading")}</p>
        ) : (
          <>
            <div className="library-heading">
              <h2>{t("library.title")}</h2>
              <span aria-live="polite">
                {t("count.series", { count: groups.length })}
              </span>
            </div>
            {groups.length === 0 && (
              <div className="empty">
                <p>{t("empty.search")}</p>
                <button
                  className="secondary"
                  onClick={() => {
                    setQuery("");
                    setSeriesFilter("all");
                  }}
                >
                  {t("empty.reset")}
                </button>
              </div>
            )}
            <div className="series-list">
              {groups.map(({ series, episodes }) => (
                <section
                  className="series"
                  key={series.id}
                  aria-labelledby={`series-${series.id}`}
                >
                  <div className="series-heading">
                    <img
                      className="series-cover"
                      src={assetUrl(series.cover)}
                      alt=""
                    />
                    <div>
                      <h3 id={`series-${series.id}`}>{series.title[locale]}</h3>
                      <p>{series.summary[locale]}</p>
                      <div className="series-links">
                        {series.links.map((link) => (
                          <a
                            key={link.url}
                            href={link.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {link.label[locale]}
                            <ArrowUpRight size={15} />
                          </a>
                        ))}
                      </div>
                    </div>
                    <span className="episode-count">
                      {episodes.length > 0 &&
                      episodes.every(
                        (episode) =>
                          episode.quality.kind === "reference-preview",
                      )
                        ? t("count.previews", { count: episodes.length })
                        : t("count.episodes", {
                            count: episodes.filter(
                              (episode) =>
                                episode.quality.kind === "verified-podcast",
                            ).length,
                          })}
                    </span>
                  </div>
                  {episodes.length === 0 ? (
                    <p className="series-empty">{t("empty.series")}</p>
                  ) : (
                    <ul className="episode-list">
                      {episodes.map((episode) => (
                        <li
                          className={`episode ${selection?.episode.id === episode.id ? "selected" : ""}`}
                          key={episode.id}
                        >
                          <button
                            className="episode-play"
                            onClick={() => choose(episode)}
                            aria-label={t("episode.play", {
                              title: episode.title[locale],
                            })}
                          >
                            <Play size={21} />
                          </button>
                          <div className="episode-content">
                            <h4>{episode.title[locale]}</h4>
                            <div className="episode-meta">
                              <span className="badge">
                                {t(
                                  episode.quality.kind === "reference-preview"
                                    ? "episode.preview"
                                    : "episode.verified",
                                )}
                              </span>
                              <span>
                                {duration(episode.audio.durationSeconds)}
                              </span>
                              <time dateTime={episode.publishedAt}>
                                {date(episode.publishedAt)}
                              </time>
                            </div>
                            <p>{episode.summary[locale]}</p>
                            {episode.quality.kind === "reference-preview" && (
                              <p className="preview-note">
                                {t("preview.note")}
                              </p>
                            )}
                            <span className="disclosure">
                              {t("disclosure")}
                            </span>
                          </div>
                          <button
                            className="text-button"
                            onClick={() => setDialog(episode)}
                          >
                            <FileText size={18} />
                            {t("episode.transcript")}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ))}
            </div>
          </>
        )}
        {supportUrl && (
          <a
            className="support-link"
            href={supportUrl}
            target="_blank"
            rel="noreferrer"
          >
            {t("support")}
          </a>
        )}
      </main>
      {selection && (
        <Player
          key={`${selection.episode.id}:${selection.episode.audio.sha256}`}
          {...selection}
          locale={locale}
          onClose={() => setSelection(undefined)}
          onTranscript={() => setDialog(selection.episode)}
        />
      )}
      {dialog && (
        <DialogBoundary
          key={typeof dialog === "string" ? dialog : dialog.id}
          fallback={
            <div className="dialog-loading" role="alert">
              <p>{t("error.detail")}</p>
              <button
                className="secondary"
                onClick={() => setDialog(undefined)}
              >
                {t("dialog.close")}
              </button>
            </div>
          }
        >
          <Suspense
            fallback={
              <p className="dialog-loading" role="status">
                {t("loading")}
              </p>
            }
          >
            {dialog === "subscribe" ? (
              <Subscribe locale={locale} onClose={() => setDialog(undefined)} />
            ) : (
              dialog && (
                <Transcript
                  key={dialog.id}
                  episode={dialog}
                  locale={locale}
                  onClose={() => setDialog(undefined)}
                  onSeek={(seconds) => {
                    choose(dialog, seconds);
                    setDialog(undefined);
                  }}
                />
              )
            )}
          </Suspense>
        </DialogBoundary>
      )}
    </>
  );
}
