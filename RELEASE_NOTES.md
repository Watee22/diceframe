# DiceFrame v2.4.0-beta.2

## 中文

DiceFrame v2.4.0-beta.2 是预览版更新，主要改进运行问题排查和更新包兼容性。

### 本次更新

- **运行日志**：DiceFrame 会保留按天轮转的运行日志，默认保留最近 30 天；可在设置中查看、清除，并与对局记录分开管理。
- **DF 助手排障**：可将脱敏后的运行日志交给 DF 助手分析，帮助定位常见启动、连接和服务调用问题。
- **设置界面**：运行日志和连接超时相关设置重新整理，信息更容易找到。
- **更新包校验**：Release 提供统一的 `SHA256SUMS` 清单，新版更新器和手动下载用户可据此校验所有压缩包。

### 预览版提示

- 这是预览版，可能包含未完成的改动或已知问题，不建议直接用于唯一的正式战役环境。
- 升级前请备份完整的 `data/` 文件夹；运行日志位于安装目录的 `logs/`（托管 Docker 为持久化 `data/logs/`）。
- 高级 DND5E 和冒险包仍处于测试阶段；传统规则、CoC、赛博朋克和 generic d20 不会自动启用 DND 专属机制。
- 预览版 Docker 镜像使用显式版本标签，不会覆盖 `latest`。Docker Update 目前仅支持 `linux-amd64`。

### 下载与校验

- Windows 便携版：`DiceFrame-v2.4.0-beta.2-windows-portable.zip`
- Windows 源码包：`DiceFrame-v2.4.0-beta.2-windows.zip`
- Docker 托管更新：`DiceFrame-v2.4.0-beta.2-docker-update-linux-amd64.zip`
- 手动下载时，请使用 `SHA256SUMS` 统一校验。
- 从 `2.3.2` 等旧版本自动升级时，旧更新器不识别 `SHA256SUMS`，因此会跳过包校验；升级功能仍可用，升级后新版更新器会恢复校验。

## English

DiceFrame v2.4.0-beta.2 is a preview release focused on runtime troubleshooting and update-package compatibility.

### What's new

- **Runtime logs**: DiceFrame keeps daily-rotated runtime logs for the latest 30 days by default. Logs can be viewed and cleared from Settings and remain separate from game history.
- **DF Assistant diagnostics**: Redacted runtime logs can be sent to DF Assistant to help identify common startup, connection, and service-call problems.
- **Settings**: Runtime-log and connection-timeout controls are grouped more clearly.
- **Update checksums**: Each Release includes one unified `SHA256SUMS` manifest for all archives. Newer updaters and manual downloads can verify packages against it.

### Preview notes

- This is a preview release and may contain unfinished changes or known issues. Do not use it as the only copy of an important production campaign.
- Back up the complete `data/` directory before upgrading. Runtime logs live under `logs/` (or persistent `data/logs/` for managed Docker).
- Advanced DND5E and adventure bundles remain beta features. Traditional rules, CoC, cyberpunk, and generic d20 do not inherit D&D-specific mechanics.
- Preview Docker images use explicit version tags and do not replace `latest`. Docker Update currently supports `linux-amd64` only.

### Downloads and verification

- Windows portable: `DiceFrame-v2.4.0-beta.2-windows-portable.zip`
- Windows source: `DiceFrame-v2.4.0-beta.2-windows.zip`
- Managed Docker update: `DiceFrame-v2.4.0-beta.2-docker-update-linux-amd64.zip`
- For manual downloads, verify all archives with `SHA256SUMS`.
- When upgrading automatically from `2.3.2` or another older version, the legacy updater does not understand `SHA256SUMS` and therefore skips package verification. The update still works; verification resumes after the new updater is installed.
