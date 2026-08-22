# DiceFrame v2.3.0-beta.1

## 中文

DiceFrame 2.3.0-beta.1 为预览版：新增「联机冒险」玩家直连能力（实验性），并强化多人局的安全与公平性。

### 新增

- **玩家直连（实验性）**：无需自建服务器，房主创建临时直连房间，为每位玩家生成独立的一次性链接码；朋友粘贴链接码即可加入同一场冒险。连接信息仅用于短暂握手，直连成功后游戏数据在参与者之间直接传输。
- **联机冒险入口**：总览页新增「联机冒险」按钮，在同一窗口内完成创建房间或粘贴链接码加入。

### 改进

- **多人公平性保护**：系统明确玩家与 GM 的权限边界——单个玩家的叙述不能改写世界事实、NPC 或其他玩家的角色状态，多人同局体验更可靠。
- **联机体验**：邀请码列表更紧凑，支持一键复制全部链接码；连接失败提示改为可读文案；房主离开后房间自动废弃，避免朋友拿着失效链接码空等。
- **骰子与判定可靠性**：D&D 普通属性/技能检定统一按 `d20 + 修正值 >= DC` 结算，不再要求自然 20 才能成功；CoC 奖惩骰会先构造最终百分骰结果再取高/取低，正确处理 `00 + 0 = 100`。
- **规则能力显式化**：内置奇幻、赛博朋克、武侠与 CoC 规则明确声明优势/劣势或奖惩骰能力；多人有效协助可按规则转换为优势，长团难度不会随回合数自动抬高。现有存档无需转换。

### 已知限制

- 直连为实验性功能：对称 NAT、严格防火墙等网络环境可能无法连通；链接码 5 分钟有效且一次性使用；房主必须保持 DiceFrame 和房间在线。
- 当前直连只传输明确支持的游戏 JSON 操作，不传输语音识别音频或其他二进制附件；相关入口会隐藏或回退到内置资源。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v2.3.0-beta.1-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v2.3.0-beta.1-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

DiceFrame 2.3.0-beta.1 is a preview release: it introduces the experimental "Multiplayer Adventure" player-to-player direct connect, and hardens fairness and safety for multiplayer sessions.

### New

- **Player-to-player direct connect (experimental)**: no self-hosted server needed — the host creates a temporary room and issues an independent one-time link code per player; friends paste a code to join the same adventure. Connection details are exchanged only for the brief handshake; once connected, game data travels directly between participants.
- **Multiplayer Adventure entry**: the overview page gains a "Multiplayer Adventure" button that handles room creation and code-based joining in one window.

### Improvements

- **Multiplayer fairness protection**: the system enforces the authority boundary between players and the GM — one player's narration can no longer rewrite world facts, NPCs, or other players' character states.
- **Connect UX**: a more compact invite-code list with copy-all, readable failure messages, and rooms that expire once the host leaves so friends never wait on a dead code.
- **Reliable dice resolution**: ordinary D&D ability/skill checks consistently resolve as `d20 + modifier >= DC` and no longer require a natural 20 to succeed. CoC bonus/penalty dice compare completed percentile results and correctly treat `00 + 0` as 100.
- **Explicit rule capabilities**: bundled fantasy, cyberpunk, wuxia, and CoC rules explicitly declare advantage/disadvantage or bonus/penalty support. Effective multiplayer assistance can grant advantage where the rule allows it, and difficulty does not rise automatically with campaign length. Existing saves require no conversion.

### Known limits

- Direct connect is experimental: symmetric NAT or strict firewalls may prevent a connection; link codes are one-time and expire after five minutes; the host must keep DiceFrame and the room online.
- The current direct transport carries explicitly supported JSON game operations, not speech-recognition audio or other binary attachments. Affected UI entry points are hidden or fall back to bundled assets.

### Download Guide

- **Regular Windows users**: download `DiceFrame-v2.3.0-beta.1-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v2.3.0-beta.1-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.
