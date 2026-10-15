---
name: babel-fetch
description: 巴别塔 Babel — 抓取播客单集或访谈视频/音频为 source.mp3。当用户要给巴别塔添加一期节目、提供一个 YouTube/B 站/播客链接要求转中文时使用。
---

# babel-fetch：抓取源音频

工作目录：`apps/pipeline/`（monorepo 根下的 venv 在 `apps/pipeline/.venv`）。

## 播客 RSS 单集

```bash
cd apps/pipeline
.venv/bin/python pipeline/fetch.py --list          # 找序号
.venv/bin/python pipeline/fetch.py --download <N>  # 下载
```

## 任意视频/音频页（YouTube、B 站、archive.org…）

只抽音轨，不下载画面：

```bash
cd apps/pipeline
.venv/bin/python pipeline/fetch_video.py "<URL>" [--slug 名字]
```

## YouTube 风控（403 / "not a bot"）

`secrets/cookies.txt` 存在时 `fetch_video.py` 会自动使用。
失效时让用户在浏览器登录 YouTube 后运行：

```bash
scripts/cookies_refresh.sh [chrome|firefox|edge|brave]
```

## 产物

`episodes/<slug>/source.mp3` + `meta.json`。下一步交给 babel-convert。
