# 巴别塔 Babel — Web（占位）

两部分，可能同站也可能分开部署：

## 1. 产品介绍页（landing）

- 是什么：英文访谈/播客 → 中文音频，RSS 自由订阅
- 单集列表、试听、订阅引导（小宇宙 / Apple / Spotify / 泛用客户端）
- 现阶段由 `apps/pipeline/docs/index.html`（GitHub Pages 静态页）临时承担，
  本产品页上线后取而代之

## 2. Web 客户端

- 订阅 `feed.xml`（也可支持任意 RSS 源）
- 在线播放 + 进度记忆
- 中英对照字幕（数据源：`apps/pipeline/episodes/*/transcript_{en,zh}.srt`）

## 与 pipeline 的关系

- 数据入口 = pipeline 输出的 `docs/feed.xml`（GitHub Pages）与 Releases 音频
- 若做动态站，考虑把 build_feed.py 的产物改为构建期数据（SSG），moon 里
  用 `dependsOn: ['pipeline']` 表达这层依赖
