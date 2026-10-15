import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Play, Pause, RotateCcw, RotateCw, X, FileText } from "lucide-react";
import type { Episode, Locale } from "@babel/catalog";
import { clock } from "./data";
import { readPreference, savePreference } from "./i18n";

export default function Player({
  episode,
  request,
  startAt,
  locale,
  onClose,
  onTranscript,
}: {
  episode: Episode;
  request: number;
  startAt?: number;
  locale: Locale;
  onClose: () => void;
  onTranscript: () => void;
}) {
  const { t } = useTranslation();
  const audio = useRef<HTMLAudioElement>(null);
  const panel = useRef<HTMLElement>(null);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(episode.audio.durationSeconds);
  const [rate, setRate] = useState(() => {
    const saved = Number(readPreference("babel-speed"));
    return [0.75, 1, 1.25, 1.5, 2].includes(saved) ? saved : 1;
  });
  const lastSave = useRef(0);
  const restored = useRef(false);
  const key = `babel-progress:${episode.id}:${episode.audio.sha256}`;
  const persist = (element: HTMLAudioElement) => {
    if (!restored.current) return;
    savePreference(key, String(element.ended ? 0 : element.currentTime));
    lastSave.current = element.currentTime;
  };
  useEffect(() => {
    const element = panel.current!;
    const observer = new ResizeObserver(() =>
      document.documentElement.style.setProperty(
        "--player-space",
        `${element.getBoundingClientRect().height + 24}px`,
      ),
    );
    observer.observe(element);
    const media = audio.current!;
    return () => {
      observer.disconnect();
      persist(media);
      media.pause();
      document.documentElement.style.removeProperty("--player-space");
    };
  }, []);
  useEffect(() => {
    if (audio.current) audio.current.playbackRate = rate;
    savePreference("babel-speed", String(rate));
  }, [rate]);
  const startPlayback = () => {
    const element = audio.current!;
    setError(false);
    if (element.error) {
      restored.current = false;
      element.load();
    }
    return element.play();
  };
  useEffect(() => {
    const element = audio.current!;
    let cancelled = false;
    if (startAt != null && element.readyState >= 1)
      element.currentTime = Math.min(startAt, duration);
    void startPlayback().catch((failure: DOMException) => {
      if (!cancelled && failure.name !== "AbortError") setError(true);
    });
    return () => {
      cancelled = true;
    };
  }, [request]);
  const toggle = () => {
    const element = audio.current!;
    if (!element.paused) element.pause();
    else
      void startPlayback().catch((failure: DOMException) => {
        if (failure.name !== "AbortError") setError(true);
      });
  };
  const seek = (value: number) => {
    if (audio.current && audio.current.readyState >= 1)
      audio.current.currentTime = Math.min(duration, Math.max(0, value));
  };
  return (
    <section className="player" ref={panel} aria-label={t("player.label")}>
      <audio
        ref={audio}
        src={episode.audio.url}
        preload="metadata"
        onLoadedMetadata={(event) => {
          const media = event.currentTarget;
          if (Number.isFinite(media.duration)) setDuration(media.duration);
          const saved = startAt ?? Number(readPreference(key));
          if (Number.isFinite(saved) && saved > 0 && saved < media.duration - 1)
            media.currentTime = saved;
          restored.current = true;
          setPosition(media.currentTime);
          media.playbackRate = rate;
        }}
        onPlay={() => {
          setPlaying(true);
          setError(false);
        }}
        onPlaying={() => setLoading(false)}
        onWaiting={() => setLoading(true)}
        onCanPlay={() => setLoading(false)}
        onPause={(event) => {
          setPlaying(false);
          setLoading(false);
          persist(event.currentTarget);
        }}
        onEnded={(event) => {
          setPlaying(false);
          persist(event.currentTarget);
        }}
        onError={() => {
          setError(true);
          setPlaying(false);
          setLoading(false);
        }}
        onTimeUpdate={(event) => {
          const media = event.currentTarget;
          setPosition(media.currentTime);
          if (Math.abs(media.currentTime - lastSave.current) >= 5)
            persist(media);
        }}
      />
      <div className="player-info">
        <strong>{episode.title[locale]}</strong>
        <span>{t("disclosure")}</span>
      </div>
      <div className="transport">
        <button
          className="icon-button"
          onClick={() => seek(position - 15)}
          aria-label={t("player.back")}
        >
          <RotateCcw size={20} />
        </button>
        <button
          className="play-button"
          onClick={toggle}
          aria-label={t(playing ? "player.pause" : "player.play")}
        >
          {playing ? <Pause size={22} /> : <Play size={22} />}
        </button>
        <button
          className="icon-button"
          onClick={() => seek(position + 15)}
          aria-label={t("player.forward")}
        >
          <RotateCw size={20} />
        </button>
      </div>
      <div className="player-progress">
        <input
          type="range"
          min="0"
          max={duration}
          step="0.1"
          value={position}
          onChange={(event) => seek(Number(event.target.value))}
          aria-label={t("player.seek")}
          aria-valuetext={t("player.position", {
            current: clock(position),
            total: clock(duration),
          })}
        />
        <div>
          <time>{clock(position)}</time>
          <time>{clock(duration)}</time>
        </div>
      </div>
      <div className="speed">
        <select
          aria-label={t("player.speed")}
          value={rate}
          onChange={(event) => setRate(Number(event.target.value))}
        >
          {[0.75, 1, 1.25, 1.5, 2].map((value) => (
            <option key={value} value={value}>
              {t("player.speed.value", {
                rate: new Intl.NumberFormat(locale).format(value),
              })}
            </option>
          ))}
        </select>
      </div>
      <button
        className="icon-button"
        onClick={onTranscript}
        aria-label={t("episode.transcript")}
      >
        <FileText size={20} />
      </button>
      <button
        className="icon-button player-close"
        onClick={onClose}
        aria-label={t("player.close")}
      >
        <X size={20} />
      </button>
      {(error || loading) && (
        <p className="player-status" role={error ? "alert" : "status"}>
          {t(error ? "player.error" : "player.loading")}
        </p>
      )}
    </section>
  );
}
