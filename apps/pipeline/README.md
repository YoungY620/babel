# Acquired 中文精译 — 转换 + 公网播客发布流水线

把 Acquired 播客单集转成中文音频，通过 **GitHub Pages（RSS + 网页播放器）+ GitHub Releases（音频托管）** 免费公网发布，RSS 可提交到小宇宙 / Apple Podcasts / Spotify 变成真正的平台播客。

## 架构

```
acquired.fm RSS ──fetch──> source.mp3 ──faster-whisper──> transcript_en
                                              │
                              OpenAI 兼容 API 翻译 (translate.py)
                                              ▼
                                    transcript_zh ──edge-tts──> zh.mp3
                                              │
                 GitHub Releases (tag: audio) │  GitHub Pages (docs/)
                     zh 音频 CDN              ▼   feed.xml + index.html
                                   小宇宙 / Apple / Spotify 提交 RSS
```

- 音频文件：GitHub Releases 资产（单文件上限 2GB，免费 CDN），仓库本体不放大文件
- RSS/播放器：GitHub Pages，源 = `main` 分支 `/docs`
- 全部免费；只有翻译调用 LLM API 有少量费用（也可用本地模型）

## 首次设置

```bash
python3 -m venv .venv && .venv/bin/pip install edge-tts faster-whisper mutagen
cp config.env.example config.env   # 填 GITHUB_USER / GITHUB_REPO 等
export OPENAI_API_KEY=...          # translate.py 用，OPENAI_BASE_URL 可选
```

## 处理一集

```bash
.venv/bin/python pipeline/fetch.py --list                 # 看单集列表
.venv/bin/python pipeline/fetch.py --download 217         # 下载某一集
.venv/bin/python pipeline/transcribe.py <slug>            # 英文转录 (large-v3-turbo)
.venv/bin/python pipeline/translate.py <slug>             # 翻译成中文
.venv/bin/python pipeline/tts.py <slug>                   # 中文 TTS -> zh.mp3
.venv/bin/python pipeline/build_feed.py                   # 生成 docs/feed.xml + 播放器
bash pipeline/publish.sh                                  # 传 Release + 推 Pages
```

> 注意：Acquired 一集常 3–6 小时。CPU 上 large-v3-turbo 转录约 0.5–1× 实时，
> TTS 约 0.3× 实时。建议先用短单集（如 trailer-what-is-acquired, 2.5 分钟）验证。

## 发布到平台

1. `bash pipeline/publish.sh` 后拿到 `https://<user>.github.io/<repo>/feed.xml`
2. 小宇宙：创作者中心 → 新建节目 → 通过 RSS 链接创建
3. Apple Podcasts Connect → 添加有 RSS Feed 的节目
4. Spotify for Creators → Add show → 已有 RSS
5. 网页播放器地址直接分享即可在线播放

## 视频来源：只抽音轨（访谈视频 → 同一管线）

本管线专注音频。访谈视频（YouTube / B 站 / archive.org…）不处理画面，
用 `fetch_video.py` 抽音轨后走完全相同的后续步骤：

```bash
.venv/bin/python pipeline/fetch_video.py "<视频URL>" [--slug 名字]
# 然后照常 transcribe.py / translate.py / tts.py / build_feed.py
```

- 音轨统一转成 64kbps 单声道 mp3（人声足够，6 小时仅 ~130MB）
- **YouTube 风控**：裸连常遇 "Sign in to confirm you're not a bot"。用浏览器 cookies 绕过：

  ```bash
  YTDLP_EXTRA_ARGS="--cookies-from-browser chrome" .venv/bin/python pipeline/fetch_video.py "<url>"
  ```

- B 站公开视频通常可直接解析；yt-dlp 需保持新版（venv 内已装官方最新 binary，
  旧版会被 YouTube 403）

## 版权提醒

Acquired 节目受版权保护。**私下转录翻译给自己听没问题；公网发布中文配音/字幕版
属于衍生作品，需要取得 Acquired 授权**（他们有官方翻译授权合作的先例，可邮件
联系）。未授权公开发布有被平台下架/版权投诉的风险，请自行评估。
