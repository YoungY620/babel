# Ubuntu runner

在与 Research Agent 共用的 Ubuntu x86_64 主机上，以 root 运行 `install-runner.sh`。
将 GitHub 仓库 runner 注册 API 返回的临时 token 通过标准输入传入；不要将 token 写入命令历史或 Git。
安装包版本和 SHA-256 固定在脚本中，注册完成后由 GitHub runner 自更新。

服务以 `babel-runner` 用户运行，目录为 `/srv/babel`，不加入 sudo 或 Docker 组。
GitHub 标签为 `self-hosted,Linux,X64,babel`。仅受信任分支的手动任务和定时任务使用该 runner；PR 检查使用 GitHub 托管 runner。

默认限制为最多 2 个 vCPU（四核主机的一半）、8 GiB 内存；6 GiB 后开始回收内存。
CPU/IO 权重和 nice 值降低 Babel 对其他进程的影响。CPU 配额是硬上限，低权重不能保证其他工作零延迟。
Research Agent 的实际高峰需求包含独立执行容器，不能从后端 Pod 的内存请求推断最低所需资源。

服务名可从 `/srv/babel/runner/.service` 读取。用 `systemctl status`、`journalctl -u` 检查状态。
先运行 convert 工作流的 `smoke=true` 模式，验证 Ubuntu、Python、FFmpeg、Moon 和权限隔离；该模式不会转换或发布内容。
