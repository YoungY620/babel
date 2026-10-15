# 巴别塔 Babel

> 把英文访谈和播客变成中文音频（原嗓音克隆配音）与中文文字版，
> 通过播客 RSS 和网页播放器公网分发。

## 这是什么

一个自动化管线：抓取英文播客/访谈（RSS 或视频音轨）→ AI 转录并区分说话人 →
翻译成中文 → 用每位说话人自己的嗓音合成中文配音 → 附带润色后的中文文字版 →
发布到 GitHub Pages + Releases，任何播客客户端订阅 RSS 即可收听。

设计决策记录见 [DECISIONS.md](DECISIONS.md)。

## 仓库结构

```
apps/
  pipeline/    转换流水线（核心）：抓取 → 转录 → 说话人分离 → 翻译 → 克隆配音
               → 文字版润色 → 发布（Pages RSS/播放器 + Releases 音频）
  ios/         （规划中）iOS 播客客户端
  web/         （规划中）产品介绍页 + Web 播客客户端
skills/        babel-fetch / babel-convert / babel-humanize / babel-publish
scripts/       cookies_refresh.sh（YouTube cookies）、privacy_check.sh（隐私扫描）
.github/workflows/
  convert.yml  每周定时转换（本机 self-hosted runner 执行）
  pages.yml    Pages 部署
```

## 快速开始

```bash
pnpm install
git config core.hooksPath .githooks   # 启用推送前隐私拦截

cd apps/pipeline
/opt/homebrew/bin/python3.12 -m venv .venv   # 需要 3.10–3.12
.venv/bin/pip install "numpy<2" edge-tts faster-whisper mutagen yt-dlp \
  resemblyzer "coqui-tts[codec]" "transformers>=4.57,<5" "setuptools<81" pypinyin
curl -sL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos \
  -o .venv/bin/yt-dlp && chmod +x .venv/bin/yt-dlp
cp config.env.example config.env   # 填 GitHub 账号信息
export OPENAI_API_KEY=...          # 翻译/润色用
export ELEVENLABS_API_KEY=...      # 可选：声纹克隆首选后端

.venv/bin/python pipeline/convert.py --cycle    # 处理本周期全部批次
bash pipeline/publish.sh                        # 发布到 Pages + Releases
```

发布后：

- RSS：`https://<user>.github.io/babel/feed.xml`（可订阅到小宇宙 / Apple / Spotify）
- 播放器与文字版：`https://<user>.github.io/babel/`

## 常用操作

| 需求 | 命令（apps/pipeline 下） |
|---|---|
| 看节目源/单集 | `.venv/bin/python pipeline/fetch.py --list [--show <id>]` |
| 转指定单集 | `.venv/bin/python pipeline/convert.py --index N --show <id>` |
| 转视频/音频页 | `.venv/bin/python pipeline/convert.py --url "<URL>"` |
| 转本周期批次 | `.venv/bin/python pipeline/convert.py --cycle` |
| 只重建页面/feed | `.venv/bin/python pipeline/build_feed.py` |
| 新增节目源 | 编辑 `shows.json` 加一条 |

每周期批次范围：全部未上线单集（最新优先），仅当批次同时超过 8 小时且
超过 5 集时截断。

## 定时自动转换

1. 仓库 Settings → Actions → Runners 注册本机 self-hosted runner 并常驻运行
2. 仓库 Secrets 添加 `OPENAI_API_KEY`（必需）、`ELEVENLABS_API_KEY`（可选）
3. 每周二 12:00（北京）自动跑一批；失败当天 17:00、之后每天 12:00/17:00 重试，
   本周成功后跳过；Actions 页面可手动 dispatch（指定 URL/单集，绕过周门控）
4. Mac 睡眠时任务不执行，注意电源设置

## 声纹克隆用法

管线自动完成：分离说话人（SPEAKER_XX）→ 每人剪 ~60s 样本 → 逐段克隆合成。

- 设 `ELEVENLABS_API_KEY` 即自动用 ElevenLabs（首选）；否则本地 XTTS v2；
  再不行 edge-tts 多音色兜底。可用 `--backend` 强制指定
- 样本在 `episodes/<slug>/samples/`，可人工替换更干净的片段
- ElevenLabs 的 voice_id 缓存于 `voices.json`（gitignore），跨集复用；
  某集说话人映射不对时检查 `diarization.json` 后手工调整

## YouTube 抓取

YouTube 有机器人风控。首次在浏览器登录 YouTube 后运行
`scripts/cookies_refresh.sh chrome` 导出 cookies（gitignore），
之后自动生效；失效重跑即可。B 站等平台无需此步骤。

## 赞助链接

赞助平台只用 Ko-fi。注册后把主页链接填进 `config.env`：

```
SUPPORT_LINKS="Ko-fi=https://ko-fi.com/<你的名字>"
```

再跑 `build_feed.py` 即出现在首页与 feed 说明。

## 隐私

仓库、Pages、Release 资产全部公开。提交规范见 **PRIVACY.md**（只许 noreply
邮箱、禁公司标识/本机路径/凭据）；`scripts/privacy_check.sh` 本地自检，
pre-push hook 与 CI 强制拦截。

## 版权提醒

第三方节目内容受版权保护。**私下转录翻译给自己听没问题；公网发布中文配音/
文字版属于衍生作品，需要取得原作者授权**。克隆真实人物嗓音另涉及
声音权/肖像权，比文字翻译更敏感。未授权公开发布有被下架/投诉风险，请自行评估。
