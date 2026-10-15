#!/usr/bin/env python3
"""中文 TTS -> zh.mp3。逐段用对应说话人的嗓音合成。

后端（--backend auto 时自动选择）：
  elevenlabs — ElevenLabs（首选，最成熟）：用 samples/SPEAKER_XX.wav 做
               Instant Voice Clone（voice_id 缓存在 voices.json 跨集复用），
               eleven_multilingual_v2 合成中文。需 ELEVENLABS_API_KEY。
  xtts       — XTTS v2 本地克隆（免费兜底，需 diarize.py + samples.py 产物）
  edge       — edge-tts（无克隆；不同说话人映射不同中文音色）

Usage: tts.py <slug> [--backend auto|elevenlabs|xtts|edge] [--rate +0%]
"""
import argparse, asyncio, json, os, subprocess, tempfile, urllib.request, uuid
from pathlib import Path
import os as _os
_os.environ["PATH"] = "/opt/homebrew/bin" + _os.pathsep + _os.environ.get("PATH", "")  # 规避 ~/.local/bin 下不可执行的 x86 ffmpeg

os.environ.setdefault("COQUI_TOS_AGREED", "1")  # XTTS v2 CPML，见 https://coqui.ai/cpml

ROOT = Path(__file__).resolve().parent.parent
CHUNK_CHARS = 180          # 单次合成的舒适长度
EDGE_VOICES = ["zh-CN-YunjianNeural", "zh-CN-YunxiNeural", "zh-CN-XiaoxiaoNeural",
               "zh-CN-YunzeNeural", "zh-CN-XiaoyiNeural"]
EL_MODEL = "eleven_multilingual_v2"
VOICES_JSON = ROOT / "voices.json"

_xtts = None


# ---------- elevenlabs ----------

def load_voice_cache():
    return json.loads(VOICES_JSON.read_text()) if VOICES_JSON.exists() else {}


def el_request(path, data=None, headers=None, raw=None):
    key = os.environ["ELEVENLABS_API_KEY"]
    req = urllib.request.Request(
        f"https://api.elevenlabs.io{path}", data=data,
        headers={"xi-api-key": key, **(headers or {})})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read() if raw else json.load(r)


def el_ensure_voice(show_id: str, speaker: str, wav: Path) -> str:
    """Instant Voice Clone（每 show+speaker 只建一次，voice_id 缓存在 voices.json）。"""
    cache = load_voice_cache()
    vid = cache.get(show_id, {}).get(speaker, {}).get("voice_id")
    if vid:
        return vid
    boundary = uuid.uuid4().hex
    parts = []
    def field(name, value):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f'name="{name}"\r\n\r\n{value}\r\n'.encode())
    def filefield(name, path):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f'name="{name}"; filename="{path.name}"\r\n'
                     f"Content-Type: audio/wav\r\n\r\n".encode()
                     + path.read_bytes() + b"\r\n")
    field("name", f"babel-{show_id}-{speaker}")
    field("description", f"auto-cloned by babel pipeline ({show_id} {speaker})")
    filefield("files", wav)
    parts.append(f"--{boundary}--\r\n".encode())
    res = el_request("/v1/voices/add", data=b"".join(parts),
                     headers={"content-type": f"multipart/form-data; boundary={boundary}"})
    vid = res["voice_id"]
    cache.setdefault(show_id, {})[speaker] = {"voice_id": vid, "sample": wav.name}
    VOICES_JSON.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    print(f"cloned voice {show_id}/{speaker} -> {vid}")
    return vid


def el_tts(text: str, voice_id: str, out: Path):
    audio = el_request(
        f"/v1/text-to-speech/{voice_id}",
        data=json.dumps({"text": text, "model_id": EL_MODEL}).encode(),
        headers={"content-type": "application/json"}, raw=True)
    out.write_bytes(audio)


def synth_elevenlabs(chunks, d: Path, show_id: str, td: Path):
    samples = d / "samples"
    speakers = {sp for sp, _ in chunks}
    voices = {}
    for sp in speakers:
        wav = samples / f"{sp}.wav"
        if not wav.exists():
            wav = samples / "SPEAKER_00.wav"
        voices[sp] = el_ensure_voice(show_id, sp, wav)
    parts = []
    for i, (sp, text) in enumerate(chunks):
        p = td / f"part{i:04d}.mp3"
        if p.exists() and p.stat().st_size > 0:   # 续跑：跳过已完成块
            parts.append(p)
            continue
        el_tts(text, voices[sp], p)
        parts.append(p)
        print(f"\relevenlabs {i+1}/{len(chunks)}", end="", flush=True)
    print()
    return parts


# ---------- xtts ----------

def get_xtts():
    global _xtts
    if _xtts is None:
        from TTS.api import TTS
        device = os.environ.get("TTS_DEVICE", "cpu")
        _xtts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    return _xtts


def synth_xtts(chunks, samples_dir: Path, td: Path):
    tts = get_xtts()
    parts = []
    for i, (sp, text) in enumerate(chunks):
        wav_in = samples_dir / f"{sp}.wav"
        if not wav_in.exists():
            wav_in = samples_dir / "SPEAKER_00.wav"
        p = td / f"part{i:04d}.wav"
        if p.exists() and p.stat().st_size > 0:   # 续跑：跳过已完成块
            parts.append(p)
            continue
        tts.tts_to_file(text=text, speaker_wav=str(wav_in),
                        language="zh-cn", file_path=str(p))
        parts.append(p)
        print(f"\rxtts {i+1}/{len(chunks)}", end="", flush=True)
    print()
    return parts


# ---------- edge ----------

async def synth_edge(text, voice, rate, out):
    import edge_tts
    c = edge_tts.Communicate(text, voice, rate=rate)
    with open(out, "wb") as f:
        async for chunk in c.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def synth_edge_all(chunks, rate, td: Path):
    parts = []
    for i, (sp, text) in enumerate(chunks):
        idx = int(sp.split("_")[-1]) if sp.startswith("SPEAKER_") else 0
        p = td / f"part{i:04d}.mp3"
        if p.exists() and p.stat().st_size > 0:   # 续跑：跳过已完成块
            parts.append(p)
            continue
        asyncio.run(synth_edge(text, EDGE_VOICES[idx % len(EDGE_VOICES)], rate, p))
        parts.append(p)
        print(f"\redge {i+1}/{len(chunks)}", end="", flush=True)
    print()
    return parts


# ---------- main ----------

def chunk_by_speaker(segs):
    chunks, cur_sp, cur, n = [], None, [], 0
    for s in segs:
        sp = s.get("speaker", "SPEAKER_00")
        t = (s.get("text_zh") or s["text"]).strip().rstrip("。.!！")
        if (sp != cur_sp or n + len(t) > CHUNK_CHARS) and cur:
            chunks.append((cur_sp, "。".join(cur)))
            cur, n = [], 0
        cur_sp = sp
        cur.append(t)
        n += len(t)
    if cur:
        chunks.append((cur_sp, "。".join(cur)))
    return chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--backend", default="auto",
                    choices=["auto", "elevenlabs", "xtts", "edge"])
    ap.add_argument("--rate", default="+0%")
    args = ap.parse_args()

    d = ROOT / "episodes" / args.slug
    meta = json.loads((d / "meta.json").read_text())
    segs = json.loads((d / "transcript_zh.json").read_text())
    chunks = chunk_by_speaker(segs)

    backend = args.backend
    if backend == "auto":
        if os.environ.get("ELEVENLABS_API_KEY"):
            backend = "elevenlabs"
        elif (d / "samples").is_dir() and any((d / "samples").glob("*.wav")):
            backend = "xtts"
        else:
            backend = "edge"
    print(f"{len(chunks)} chunks, backend={backend}")

    parts_dir = d / ".tts_parts" / backend   # 逐块落盘，中断可续跑
    parts_dir.mkdir(parents=True, exist_ok=True)
    if backend == "elevenlabs":
        parts = synth_elevenlabs(chunks, d, meta.get("show", "other"), parts_dir)
    elif backend == "xtts":
        parts = synth_xtts(chunks, d / "samples", parts_dir)
    else:
        parts = synth_edge_all(chunks, args.rate, parts_dir)
    lst = parts_dir / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c:a", "libmp3lame", "-b:a", "64k", "-ac", "1",
                    str(d / "zh.mp3")], check=True, capture_output=True)
    import shutil
    shutil.rmtree(d / ".tts_parts", ignore_errors=True)   # 完成后清理
    print(f"OK -> {d / 'zh.mp3'}")


if __name__ == "__main__":
    main()
