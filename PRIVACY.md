# 隐私与泄漏检查标准（Privacy Check Standard）

本仓库及其 GitHub Pages、Release 资产全部**公开**。任何提交到 main 的内容
都视为公网发布。本标准强制执行，手段：

1. `scripts/privacy_check.sh` — 本地/CI 均可运行的扫描脚本
2. `.githooks/pre-push` — 推送前拦截（启用：`git config core.hooksPath .githooks`）
3. `.github/workflows/convert.yml` 的 `privacy check` 步骤 — CI 兜底

## 禁止出现在仓库中的内容

| 类别 | 规则 |
|---|---|
| 真实姓名/邮箱 | git 提交者、文件内容中的邮箱只允许 `*@users.noreply.github.com` |
| 公司内部标识 | 不得出现公司域名、内部主机名、内部项目代号 |
| 本地路径 | 不得出现 `/Users/<name>/`、`/home/<name>/` 等绝对路径 |
| 凭据 | API key（`sk-…`、`ghp_…` 等）、私钥、cookies 文件，一律不得入库 |
| 机密目录/文件 | `secrets/`、`config.env`、`cookies.txt`、`.env*` 必须保持 gitignore |

## 允许的公开信息

- GitHub 用户名与 noreply 邮箱（其本身即是公开的仓库归属标识）
- 转换产物：音频（Releases）、字幕、文字版（属衍生内容，版权立场见 README）

## 提交者身份

本仓库 git 配置固定为：

```bash
git config user.name  "<GitHub 用户名>"
git config user.email "<GitHub 用户名>@users.noreply.github.com"
```

pre-push 会校验待推送提交的 author email，非 noreply 直接拒绝。

## 新增内容的自检清单

- [ ] 不含真名、真实邮箱、公司标识
- [ ] 不含本机绝对路径
- [ ] 不含任何凭据/令牌/cookies
- [ ] 新的大文件走了 gitignore 或 Releases，而非入库
- [ ] `bash scripts/privacy_check.sh` 通过
