# Ubuntu runner 和私有控制仓库

公开仓库不注册常驻 runner。公开 PR 可以修改 `runs-on`；标签不是访问控制。
执行控制仓库固定为 **YoungY620/babel-runner**，必须保持 private，并且只允许维护者写入。
其工作流源文件是本仓库的 `deploy/control-plane.yml`，通过 Codex Review 后复制到私有仓库的 `.github/workflows/convert.yml`。
公共仓库的 CI 和 Pages 使用 GitHub 托管 runner。

## 凭据与发布

控制仓库需要 `OPENAI_API_KEY` 和 `BABEL_PUBLISH_TOKEN`。发布 token 需要对公共 Babel 仓库的 contents write 权限；优先使用只授权该仓库的凭据。不得提交凭据值。
`seal-credentials` 是维护者手动运行的迁移工作流：它用目标私有仓库的 GitHub 公钥直接加密现有模型密钥。
下载产物后，以 `gh api --method PUT repos/YoungY620/babel-runner/actions/secrets/OPENAI_API_KEY --input sealed-credential.json` 写入目标 secret。
产物只有 GitHub 能解密；操作员无需读取原始密钥。公钥或 key_id 变化时，先更新 recipient 文件并重新审查。

## 安装和验收

在共享 Ubuntu x86_64 主机上，以 root 先运行 `bash install-runner.sh prepare`。
依赖与已校验的 runner 安装包就绪后，为私有仓库请求新的临时注册 token，通过标准输入传给 `bash install-runner.sh register`。
两阶段避免下载消耗注册 token 的有效期。token 不放入进程参数、历史或 Git。
安装器只接受固定的私有控制仓库；注册前仍需在 GitHub API 确认仓库的 `private` 字段为 true。

服务以 `babel-runner` 用户运行，目录 `/srv/babel`，不加入 sudo 或 Docker 组。
安装器拒绝 root、额外组、异常 home 或 sudo 权限不能确认的账号。
systemd 服务由 root 直接写入，不以 root 执行 runner 用户可修改的脚本。
GitHub 标签为 `self-hosted,Linux,X64,babel`，仅在私有仓库可见。

上限为 2 个 vCPU（四核主机的一半）、8 GiB 内存，MemoryHigh=6G，禁用 swap。
CPU/IO 权重和 nice 值降低对 Research Agent 的影响；这些值不能保证其他工作零延迟。
Research Agent 的配置上限不代表最低所需资源。
服务名为 `actions.runner.babel-ubuntu.service`，也写入 runner 目录的 `.service` 文件。

先在私有仓库手动运行 `smoke=true`，检查真实执行、资源限制、Python、FFmpeg、Moon、Git 身份与配置读取。
Smoke 不使用模型密钥和发布 token；checkout 公共源码不需要凭据。
公开配置由 `configure_pipeline.sh YoungY620/babel` 首次生成，不得存放密钥。
