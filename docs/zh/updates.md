# DiceFrame 应用更新

中文 | [English](../en/updates.md)

这里介绍 DiceFrame 主程序怎么更新。插件请在插件商店里单独更新。

## 不同安装方式

| 安装方式 | 怎么更新 |
|---|---|
| Windows 便携版 | 在设置页检查、下载并应用更新 |
| 解压的源码发布包 | 在设置页应用更新，完成后手动重启 |
| Git 开发目录 | 收到新版本提示后使用 `git pull` |
| 支持托管更新的 Docker / NAS | 在设置页下载、应用并自动回滚 |
| 旧 Docker 镜像或基础运行时升级 | 拉取最新镜像并重新创建容器 |

更新主程序不会删除存档和配置。升级前仍建议备份整个 `data/` 文件夹。

## Windows 便携版

打开“设置 → 版本更新”，按页面提示下载并应用即可。更新完成后 DiceFrame 会自动重启并刷新页面。

如果新版本无法正常启动，程序会自动回到更新前的版本。更新成功后，下载包和多余的旧版本也会自动清理。

便携版最多保留两套程序文件。初始压缩包根目录里的 `app/` 和 `python/` 算作第一套；第一次更新后它们作为回滚版本保留。第二次及后续更新成功后，程序只保留 `versions/` 中的当前版本和上一版本，并清理根目录里的旧 `app/`、`python/`。`data/`、`logs/` 和根目录启动器不属于版本副本，不会随旧版本清理。当前版本损坏时，启动器会根据版本指针尝试上一版本。用户安装的插件源码存放在 `data/plugin-packages/`，随 `data/` 跨版本保留；`app/plugins/` 仅存放随版本分发的内置与示例插件，会随旧版本清理。

DiceFrame 会在保留控制台输出的同时写入运行日志。Windows 便携版使用根目录 `logs/`，托管 Docker 使用持久化的 `data/logs/`；源码运行默认使用项目根目录 `logs/`。日志按天轮转，只保留最近 30 天，也可以在“设置 → 高级设置 → 运行日志”中手动清除。运行日志与对局记录、聊天历史和存档相互独立。

如果设置页只有新版本提示、没有应用按钮，请先到 GitHub Releases 手动下载一次最新便携版。之后即可继续在设置页更新。

## 源码发布包

从 GitHub Releases 下载并解压的源码版，可以在设置页应用更新。完成后按提示手动重启 DiceFrame。

更新前的程序文件会自动备份，失败时会尝试恢复。更新成功后只保留最近一次备份，存档和配置不会被覆盖。

如果你使用的是 Git 克隆目录，请继续使用 `git pull` 更新。

## Docker 与 NAS

Docker 用户需要先手动拉取一次支持“托管更新”的基线镜像。这个镜像使用稳定 launcher 管理 `data/_updater/docker-versions/` 中的当前和上一应用版本。完成基线迁移后，普通 DiceFrame 应用版本可以在“设置 → 版本更新”中下载和应用；容器 ID 不变，候选版本通过健康检查后才会提交，失败会自动回到上一版本。

Docker Update 清单必须显式声明 `data_rollback_safe: true`，表示该版本写入的持久数据仍可由上一版本读取。缺少声明或涉及不可逆数据迁移的版本会被托管更新器拒绝，必须改走带备份或迁移步骤的基础镜像升级，不能伪装成可自动回滚的普通更新。

Python ABI、系统动态库、CA、字体或 launcher 协议变化仍属于基础运行时升级，需要再次拉取镜像。DiceFrame 不挂载 Docker socket，也不会从容器内控制 Docker daemon。

使用 Docker Compose 部署时运行：

```bash
cd /path/to/diceframe  # 必须是存放 docker-compose.yml 的部署目录
docker compose pull
docker compose up -d
```

如果提示 `no configuration file provided: not found`，说明当前目录没有 Compose 配置文件。请进入原部署目录后重试；如果最初使用 `docker run` 启动，则应拉取新镜像后按原端口、卷和环境变量重新创建容器，不能直接套用 Compose 更新命令。

NAS 用户可以直接在设备自带的容器管理界面检查更新、拉取最新镜像并重新创建容器。请确认 `data/` 已挂载到宿主机。

用户存档、配置和插件仍位于 `data/`。`data/_updater/docker-versions/` 只是可由镜像 seed 恢复的程序副本，备份时可以排除；不要单独删除 `_updater/current.json`。传统的镜像更新方式始终可用，新镜像会使用与 GitHub Release 完全相同的 Docker 应用更新包作为 seed。

如果你从本地源码构建镜像，请拉取新源码后运行：

```bash
docker compose up -d --build
```

## 常见问题

### 检查更新出现 HTTP 403

这通常表示镜像源和 GitHub 的临时访问额度已经用完，只会影响版本检查，不影响游戏、存档或模型调用。稍后重试，或直接前往 GitHub Releases 查看即可。

### 更新失败

不要删除 `data/`。便携版和托管 Docker 会尽量自动恢复到旧版本；源码版会尝试恢复更新前的程序文件。如果仍无法启动，可以从 GitHub Releases 重新下载对应版本，并保留日志用于排查。
