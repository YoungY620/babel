---
name: babel-publish
description: 巴别塔 Babel — 构建播客 RSS/播放器并发布到 GitHub Pages + Releases。当用户要上线、更新节目源、查看发布地址时使用。
---

# babel-publish：发布

工作目录：`apps/pipeline/`。

```bash
cd apps/pipeline
.venv/bin/python pipeline/build_feed.py   # episodes/* → docs/feed.xml + docs/index.html
bash pipeline/publish.sh                  # 传 Release 音频 + 推 Pages（需 gh 已登录）
```

发布后：

- RSS：`https://<user>.github.io/babel/feed.xml`
- 播放器：`https://<user>.github.io/babel/`
- 音频 CDN：`github.com/<user>/babel/releases/download/audio/<slug>-zh.mp3`

把 RSS 提交到小宇宙（创作者中心 → 通过 RSS 创建节目）、Apple Podcasts
Connect、Spotify for Creators 即完成平台上架；之后每次 push 新集，各平台自动同步。

## 注意

- 首次需手动在仓库 Settings → Pages 开 main/docs（publish.sh 会尝试自动开，权限不足时静默跳过）
- 发布前确认 config.env 的 GITHUB_USER/GITHUB_REPO 正确
- 公开发布第三方节目的翻译配音涉及版权，见根 README 的版权提醒
