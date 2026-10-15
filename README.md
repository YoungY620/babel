# 巴别塔 Babel

> 把英文访谈和播客变成中文音频（预设音色配音）与中文文字版，
> 通过播客 RSS 和网页播放器公网分发。

## 这是什么

一个自动化管线：抓取英文播客/访谈（RSS 或视频音轨）→ 本地转录与说话人分离 → 云端转录证据与纠错 →
逐块翻译和审核 → 为每位说话人选择风格相近的预设音色，合成中文配音 → 附带润色后的中文文字版 →
发布到 GitHub Pages + Releases，任何播客客户端订阅 RSS 即可收听。

设计决策记录见 [DECISIONS.md](DECISIONS.md)。

## 仓库结构

```
apps/
  pipeline/    转换流水线（核心）：抓取 → 转录 → 说话人分离 → 翻译 → 预设音色配音
               → 文字版润色 → 发布（Pages RSS/播放器 + Releases 音频）
  web/         React 播客资料库、双语界面、播放器与文字稿
skills/        babel-fetch / babel-convert / babel-humanize / babel-publish
scripts/       setup_pipeline.sh（Ubuntu Python 环境）、cookies_refresh.sh（YouTube cookies）、privacy_check.sh（隐私扫描）
.github/workflows/
  convert.yml  执行位置提示（GitHub 托管 runner）
  pages.yml    Pages 部署
deploy/
  control-plane.yml  私有执行仓库工作流的受审源文件
  install-runner.sh Ubuntu 26.04 runner 安装器
```

## 快速开始

```bash
pnpm install
git config core.hooksPath .githooks   # 启用推送前隐私拦截

cd apps/pipeline
# Ubuntu Linux，Python 3.12、FFmpeg、Node 22、pnpm 10
cd ../..
pnpm moon run pipeline:setup
cd apps/pipeline
cp config.env.example config.env   # 填 GitHub 账号信息
export OPENAI_API_KEY=...          # 翻译、语音合成与音频校验

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

## 自动转换的执行位置

常驻 runner **只注册到私有仓库 `YoungY620/babel-runner`**，不得注册到本公开仓库。
公开 PR 能修改工作流的 `runs-on`，runner 标签不能隔离不受信任代码。

1. 按 [部署指南](deploy/README.md) 在 Ubuntu 26.04 x86_64 上准备独立账号和 systemd 服务。
2. 确认控制仓库仍为 private，再取得临时 token 并注册 runner。
3. 将受审的 `deploy/control-plane.yml` 部署到私有仓库，配置其模型和发布凭据。
4. 先手动执行 `smoke=true` 验证真实运行。安装阶段仅手动触发，日调度在质量和容量验收后启用。

资源硬上限为 2 个 vCPU、8 GiB 内存，默认单集、单进程、两线程，并降低调度优先级。
公共代码、CI、Pages 和音频分发仍在本仓库管理。

## 预设音色与质量检查

每位说话人使用固定的预设音色。通过短语音样本判断可听到的音域、音色和表达风格，
在候选男声、女声中匹配；不克隆声音，不判断真实身份。也可用 `tts.py <slug> --voice cedar` 明确指定。显式指定会保留；`--voice auto` 重新启用自动音色选择。
候选音色和风格描述集中在 `apps/pipeline/voice-presets.json`。

- TTS 使用 OpenAI 受支持的语音模型 `gpt-realtime-2.1`。
- `gpt-audio-1.5` 逐段检查漏字、重复、数字、专名、多音字、断句和语气；失败重试一次，仍失败则停止，不写完成产物。
- 保留原文问号、感叹号和句末标点；按语义和说话人分块，只修剪首尾静音，保留句内停顿，并设置明确的块间停顿。
- 最终音频目标为 -16 LUFS（±1），真峰值不高于 -1 dBTP，128 kbps 单声道 MP3。
- `speech.json` 记录文本/模型/音色指纹、生成音频时间轴与质量数据。仅有旧 `zh.mp3` 不算完成。
- `.speech_parts/` 保留已校验块以续跑。修改文本、模型、音色或语音策略后，不复用旧块。

模型审核是自动质量门，不能等同于人工盲听结论。更换模型前，用同一原创测试文本比较音色、错误、停顿、质量结果与完整耗时。
私有控制仓库部署 `deploy/evaluate-speech.yml` 到评估分支的 `convert.yml`。
评估只执行已合并到公共 `main` 的受审代码，不接受候选 SHA 输入。它通过 Moon 执行 `pipeline:evaluate`，产物仅存私有 artifact，不发布节目。

## 文本质量

默认用 `gpt-transcribe` 提供独立音频转录证据，`gpt-6-astra` 完成逐块纠错、精译与独立审核请求。
原始转录保留；完整文字稿与声音时间轴分开处理。发布必须通过文本、双语元数据和语音三项检查。
人工精修输入、模型配置与检查点说明见 [流水线说明](apps/pipeline/README.md)。

## YouTube 抓取

YouTube 有机器人风控。首次在浏览器登录 YouTube 后运行
`scripts/cookies_refresh.sh chrome` 导出 cookies（gitignore），
之后自动生效；失效重跑即可。B 站等平台无需此步骤。

## 赞助链接

赞助平台只用 Ko-fi。注册后把主页链接填进 `config.env`：

```
SUPPORT_LINKS="Ko-fi=https://ko-fi.com/<你的名字>"
```

React 构建时设置公共变量 `VITE_SUPPORT_URL=https://ko-fi.com/<name>` 显示支持链接。
Web 开发与构建见 [apps/web/README.md](apps/web/README.md)。

## 隐私

仓库、Pages、Release 资产全部公开。提交规范见 **PRIVACY.md**（只许 noreply
邮箱、禁公司标识/本机路径/凭据）；`scripts/privacy_check.sh` 本地自检，
pre-push hook 与 CI 强制拦截。

## 版权提醒

第三方节目内容受版权保护。**私下转录翻译给自己听没问题；公网发布中文配音/
文字版属于衍生作品，需要取得原作者授权**。
