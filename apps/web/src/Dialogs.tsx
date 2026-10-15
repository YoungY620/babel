import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { X, Copy, Check, Download } from "lucide-react";
import Markdown from "react-markdown";
import type { Episode, EpisodeDetail, Locale } from "@babel/catalog";
import { assetUrl, clock, loadDetail } from "./data";

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current!;
    const trigger = document.activeElement;
    element.showModal();
    return () => {
      element.close();
      if (trigger instanceof HTMLElement && trigger.isConnected)
        trigger.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="modal"
      aria-labelledby="dialog-title"
      onCancel={onClose}
      onClose={onClose}
    >
      <div className="modal-heading">
        <h2 id="dialog-title">{title}</h2>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label={t("dialog.close")}
        >
          <X size={22} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Subscribe({
  locale,
  onClose,
}: {
  locale: Locale;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState<"idle" | "done" | "error">("idle");
  const url = new URL(
    assetUrl(locale === "en" ? "feed-en.xml" : "feed.xml"),
    location.origin,
  ).href;
  return (
    <Modal title={t("subscribe.title")} onClose={onClose}>
      <p>{t("subscribe.description")}</p>
      <label className="field-label" htmlFor="feed-address">
        {t("subscribe.address")}
      </label>
      <input
        id="feed-address"
        className="feed-address"
        readOnly
        value={url}
        onFocus={(event) => event.currentTarget.select()}
      />
      <div className="dialog-actions">
        <button
          className="primary"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(url);
              setCopied("done");
            } catch {
              setCopied("error");
            }
          }}
        >
          {copied === "done" ? <Check size={18} /> : <Copy size={18} />}{" "}
          {t(copied === "done" ? "subscribe.copied" : "subscribe.copy")}
        </button>
        <a className="button secondary" href={url}>
          {t("subscribe.open")}
        </a>
      </div>
      {copied === "error" && <p role="status">{t("subscribe.failed")}</p>}
    </Modal>
  );
}
export function Transcript({
  episode,
  locale,
  onClose,
  onSeek,
}: {
  episode: Episode;
  locale: Locale;
  onClose: () => void;
  onSeek: (seconds: number) => void;
}) {
  const { t } = useTranslation();
  const [detail, setDetail] = useState<EpisodeDetail>();
  const [error, setError] = useState(false);
  const [tab, setTab] = useState<"captions" | "article">("captions");
  useEffect(() => {
    const controller = new AbortController();
    void loadDetail(episode, controller.signal)
      .then(setDetail)
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [episode.id, episode.audio.sha256]);
  return (
    <Modal title={episode.title[locale]} onClose={onClose}>
      <p className="muted">{t("disclosure")}</p>
      {episode.quality.kind === "reference-preview" && (
        <p>{t("preview.details")}</p>
      )}
      <div
        className="segmented"
        role="group"
        aria-label={t("transcript.title")}
      >
        <button
          aria-pressed={tab === "captions"}
          onClick={() => setTab("captions")}
        >
          {t("transcript.captions")}
        </button>
        <button
          aria-pressed={tab === "article"}
          onClick={() => setTab("article")}
        >
          {t("transcript.article")}
        </button>
      </div>
      {error ? (
        <p role="alert">{t("error.detail")}</p>
      ) : !detail ? (
        <p role="status">{t("loading")}</p>
      ) : tab === "article" ? (
        <article className="article">
          <Markdown>{detail.article[locale]}</Markdown>
        </article>
      ) : (
        <ol className="cue-list">
          {detail.cues.map((cue, index) => (
            <li key={index}>
              <button
                className="cue-time"
                aria-label={t("transcript.seek", { time: clock(cue.start) })}
                onClick={() => onSeek(cue.start)}
              >
                {clock(cue.start)}
              </button>
              <div>
                <span className="speaker">
                  {/SPEAKER_\d+/.test(cue.speaker)
                    ? t("transcript.speaker", {
                        number: Number(cue.speaker.split("_")[1]) + 1,
                      })
                    : t("transcript.narrator")}
                </span>
                <p>{cue.text[locale]}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
      {episode.sourceUrl && (
        <p>
          <a
            className="button secondary"
            href={episode.sourceUrl}
            target="_blank"
            rel="noreferrer"
          >
            {t("episode.source")}
          </a>
        </p>
      )}
      <a
        className="button secondary"
        href={assetUrl(episode.captions[locale])}
        download
      >
        <Download size={18} />
        {t("transcript.download")}
      </a>
    </Modal>
  );
}
