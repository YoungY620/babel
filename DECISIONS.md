# 设计决策记录（DECISIONS）

记录本项目的关键设计决策及理由。README 只写产品说明与用法，决策都放这里。

## D1 命名：巴别塔 Babel

逆转巴别塔的隐喻——让不同语言的内容归于可懂。英文名 Babel（不避与 JS
编译器重名，领域足够远），中文名「巴别塔」。

## D2 托管：GitHub Pages + GitHub Releases，RSS 即分发

- 音频文件放 Releases（单文件 2GB、总容量与下载带宽无配额、免费 CDN），
  不占用仓库体积，也不走 Git LFS（其免费额度只有 1GB）。
- RSS/播放器/文字版放 Pages（100GB/月软上限对本体量足够）。
- 「发布到平台」= 把 RSS 提交给小宇宙 / Apple / Spotify，平台定期拉源，
  无需逐平台上传。网页播放器满足公网直接收听。

## D3 纯音频定位

不处理视频画面。访谈视频（YouTube/B 站等）一律 yt-dlp 抽音轨后进入同一
音频管线。长视频不托管（2GB 放不下 720p+ 长片），如需视频版走
YouTube/B 站外链。

## D4 调度：GitHub Actions 定时 + 本机 self-hosted runner

GitHub 只做调度（cron），计算（whisper/TTS，数小时级）在用户自己的 Mac 上，
零成本。每周二 12:00（北京）首跑，失败当天 18:00 重试，之后每天 12/18 点，
直到本周成功（state.json 按 ISO 周去重）。

## D5 周期选集：全量未处理 + 联合上限

每周期处理全部未上线单集（各节目最新优先），唯一截断条件：批次**同时**
超过 8 小时且超过 5 集（即 ≤5 集时长不限、≤8 小时集数不限）。
节目源配置驱动（apps/pipeline/shows.json），加节目不改代码。

## D6 声纹克隆后端：ElevenLabs > XTTS > edge-tts

目标效果是每位说话人用原嗓音说中文。
- 首选 **ElevenLabs**（业界最成熟稳健的方案；Instant Voice Clone +
  eleven_multilingual_v2，英文样本可直接合成中文；按字符计费）。
- 无 key 时降级 **XTTS v2**（本地免费，质量次之）。
- 最终兜底 edge-tts（无克隆，仅多音色区分说话人）。
说话人分离用 resemblyzer 声纹聚类（本地，无需 HF 授权），样本每人 ~60s。

## D7 赞助：只用 Ko-fi

- Ko-fi 捐赠 0 手续费，注册即用，国际受众。
- GitHub Sponsors 个人账户也 0 抽成，但收款需支持地区银行账户
  （中国大陆不在列），不可用。
- 爱发电（国内）与加密地址暂不上线；config 已留 SUPPORT_* 槽位，
  未来变更只改配置。加密备注：EVM 普通转账无法附言，Solana Pay 的
  message 可经 memo program 上链，若启用用后者。
- OKX a2a 支付链接默认 30 分钟过期，不适合做长期收款码，不采用。

## D8 隐私：公开仓库三件套

仓库/Pages/Releases 全公开。标准见 PRIVACY.md；执行：
`scripts/privacy_check.sh`（本地+CI 共用）+ `.githooks/pre-push` 拦截。
git 身份只用 noreply 邮箱；已重写历史抹除早期含真实邮箱的提交。

## D9 monorepo：moon 轻量使用

moon 只负责项目/任务登记与调度（apps/pipeline、apps/web、apps/ios），
不开工具链托管、不用其缓存（流水线产物不适合进 moon 缓存，幂等由各
脚本按产物存在性判断）。

## D10 品牌

- 图标：阶梯金字塔（巴别塔）+ 盘旋向上的路 + 塔顶信号点。
  源文件 `apps/pipeline/docs/favicon.svg`，PNG 衍生 512/180/32。
- 用色：深底 `#14181f`/`#0f1115`，塔身 `#e8ecf3`，信号蓝 `#7ab8ff`，
  辅助朱砂 `#e2554f`（仅渐变场景）。
- 反面教材：不要用错位横条（像「左对齐」图标）、不用纯声纹柱（通用音频感、无巴别塔）。
