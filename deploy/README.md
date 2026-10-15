# Ubuntu runner

在与 Research Agent 共用的 Ubuntu x86_64 主机上，以 root 先运行 `bash install-runner.sh prepare`，安装依赖与 runner。
准备完成后，才请求 GitHub 仓库 runner 注册 API 的新临时 token，并通过标准输入传给 `bash install-runner.sh register`。
两个阶段分开，避免依赖下载消耗 token 的一小时有效期；token 不放入进程参数、命令历史或 Git。
安装包版本和 SHA-256 固定在脚本中，注册完成后由 GitHub runner 自更新。

服务以 `babel-runner` 用户运行，目录为 `/srv/babel`，不加入 sudo 或 Docker 组。若已有同名账号拥有额外组或 sudo 权限，安装器会拒绝使用。
GitHub 标签为 `self-hosted,Linux,X64,babel`。仅受信任分支的手动任务和定时任务使用该 runner；PR 检查使用 GitHub 托管 runner。

默认限制为最多 2 个 vCPU（四核主机的一半）、8 GiB 内存；6 GiB 后开始回收内存。
CPU/IO 权重和 nice 值降低 Babel 对其他进程的影响。CPU 配额是硬上限，低权重不能保证其他工作零延迟。
Research Agent 的实际高峰需求包含独立执行容器，不能从后端 Pod 的内存请求推断最低所需资源。

服务名可从 `/srv/babel/runner/.service` 读取。用 `systemctl status`、`journalctl -u` 检查状态。
先运行 convert 工作流的 `smoke=true` 模式，验证 Ubuntu、Python、FFmpeg、Moon 和权限隔离；该模式不会转换或发布内容。

工作流在 checkout 后运行 `scripts/configure_pipeline.sh`，设置 noreply Git 身份，并在首次运行时生成被忽略的公开发布配置。已有配置保留，运营者可在 runner 工作区编辑节目名称与 Ko-fi 链接；不得在此文件存放密钥。Smoke 同时检查配置能读取和 Git 作者身份可用。Python 由 uv 显式安装并加入后续步骤 PATH，不依赖系统 Python 版本。
