# 巴别塔 Babel

> 逆转巴别塔——把英文访谈和播客变成中文音频与文字版，万语归一。

monorepo（[moon](https://moonrepo.dev) 管理），组件：

```
apps/
  pipeline/    转换流水线：抓取 → faster-whisper 转录 → LLM 翻译 → edge-tts 中文配音
               → polish 文字版润色 → GitHub Releases 托管音频
               + GitHub Pages 输出 RSS / 网页播放器 / 文字版页面
  ios/         （规划中）iOS 播客客户端
  web/         （规划中）产品介绍页 + Web 播客客户端
skills/
  babel-fetch/     抓取播客单集 / 访谈视频音轨（agent skill）
  babel-convert/   转换为中文音频（agent skill）
  babel-humanize/  中文文字版润色标准（去翻译腔/AI 腔）
  babel-publish/   构建 RSS 并发布（agent skill）
scripts/
  cookies_refresh.sh   YouTube cookies 导出/刷新（长期使用 secrets/cookies.txt）
  privacy_check.sh     隐私泄漏扫描（hook 与 CI 共用，标准见 PRIVACY.md）
.github/workflows/
  convert.yml    每周转换一集（GitHub Actions 调度 + 本机 self-hosted runner）
  pages.yml      Pages 部署（monorepo 下站点在 apps/pipeline/docs，走 Actions）
```

## 快速开始

```bash
pnpm install                 # 安装 moon
git config core.hooksPath .githooks   # 启用推送前隐私拦截（见 PRIVACY.md）
pnpm moon query projects     # 应看到 pipeline + ios + web

cd apps/pipeline
python3 -m venv .venv && .venv/bin/pip install edge-tts faster-whisper mutagen yt-dlp
cp config.env.example config.env   # 填 GitHub 账号信息
export OPENAI_API_KEY=...          # 翻译/润色用

.venv/bin/python pipeline/convert.py --next     # 转最新未处理的一集（全流程，含文字版）
bash pipeline/publish.sh                        # 发布
```

发布后：`https://<user>.github.io/babel/feed.xml` 可订阅到小宇宙 / Apple / Spotify；
网页播放器与每集文字版同在 Pages 上。

## 定时自动转换（GitHub Actions + 本机 runner）

调度在 GitHub，计算在你的 Mac 上（whisper/TTS 吃本地算力，免费无限时）：

1. 仓库 Settings → Actions → Runners → New self-hosted runner → macOS，
   按指引下载 runner 并 `./run.sh`（或 `svc.sh` 装成开机服务）
2. 仓库 Settings → Secrets → Actions 添加 `OPENAI_API_KEY`
3. `.github/workflows/convert.yml` 每周二 12:00（北京时间）首次尝试转换；
   失败（如 runner 不在线）→ 当天 18:00 重试 → 之后每天 12:00/18:00 重试，
   直到本周成功（`apps/pipeline/state.json` 记录，后续触发自动跳过）。
   也可 Actions 页面手动 dispatch 指定 URL / 单集序号（绕过周门控）
4. 每周处理哪些集由 `apps/pipeline/shows.json` 决定：
   - `backlog` 模式（Acquired）：每周消化该节目最新一集未处理的
   - `recent` 模式（Dwarkesh Podcast）：处理 `recent_days` 窗口内更新的**全部**新集
   - 新增节目：往 shows.json 加一条即可
5. 注意：Mac 睡眠时任务不执行；系统设置里可接电源时防睡眠

## YouTube cookies（长期）

YouTube 对数据中心/陌生 IP 有机器人风控。首次在某浏览器登录 YouTube 后：

```bash
scripts/cookies_refresh.sh chrome   # 导出到 secrets/cookies.txt（gitignore）
```

之后 `fetch_video.py` 自动使用；失效（403 / not a bot）时重跑即可。

## 隐私

本仓库、Pages、Release 资产全部公开。提交前必读 **PRIVACY.md**：
只使用 noreply 邮箱提交、禁公司内部标识、禁本机绝对路径、禁凭据。
`scripts/privacy_check.sh` 本地自检；`.githooks/pre-push` 推送拦截；
convert workflow 里也有同一道检查。

## 版权提醒

第三方节目（如 Acquired）的内容受版权保护。**私下转录翻译给自己听没问题；
公网发布中文配音/文字版属于衍生作品，需要取得原作者授权**。未授权公开发布有被
平台下架/版权投诉的风险，请自行评估。
