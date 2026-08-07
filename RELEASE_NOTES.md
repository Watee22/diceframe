# DiceFrame v1.9.12-beta.2

## 中文

这是一个预览版，主要测试**一键外网接入**（Cloudflare 快速隧道插件）和插件商店生态的改进。预览版用户可以更新体验；正式版频道不受影响。

### 新功能

- **外网接入插件**：新增官方 **Cloudflare 快速隧道** 插件，可一键生成公网 HTTPS 地址并自动写入分享链接，朋友和群聊 Bot 无需公网 IP 或域名即可访问你的对局。在"插件 → 工具"页的外网接入卡片操作，需 DiceFrame 1.9.12 及以上。插件已上架商店，也可从商店安装。
- **工具页专用界面**：工具型插件现在可以在工具页展示专用操作卡片（如外网接入卡），不再只显示裸的 JSON 参数调用界面。
- **插件商店版本标注**：商店条目会显示插件所需的 DiceFrame 最低版本；安装/更新前会提示"需升级 DiceFrame 至 X 及以上"。
- **商店包体放宽**：支持更大体积的插件包，为带二进制组件的进程型插件做准备。

### 体验改进

- 设置页"外网接入"选项卡移除，统一由"插件 → 工具"页的外网接入卡片承担。
- 用户手册新增"Cloudflare 快速隧道插件"小节，说明安装与使用方式。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v1.9.12-beta.2-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v1.9.12-beta.2-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

This preview release focuses on **one-click external access** (Cloudflare quick tunnel plugin) and plugin store ecosystem improvements. Preview-channel users can update and try it; the stable channel is unaffected.

### New Features

- **External access plugin**: a new official **Cloudflare quick tunnel** plugin generates a public HTTPS address with one click and writes it to the share link automatically, so friends and chat bots can reach your table without a public IP or domain. Operate it from the external-access card on the Plugins → Tools page; requires DiceFrame 1.9.12 or later. The plugin is published to the store and can be installed from there.
- **Dedicated tool UI**: tool plugins can now render a dedicated operation card on the Tools page (such as the external-access card) instead of only a raw JSON-argument form.
- **Plugin store version badge**: store entries show the minimum DiceFrame version a plugin requires; install/update flows prompt "requires DiceFrame X or later".
- **Larger plugin packages**: the store accepts larger plugin packages to prepare for process plugins that bundle binaries.

### Improvements

- The "External Access" section in Settings was removed; it is now served by the external-access card on the Plugins → Tools page.
- The user guide gained a "Cloudflare quick tunnel plugin" section covering install and usage.

### Download Guide

- **Regular Windows users**: download `DiceFrame-v1.9.12-beta.2-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v1.9.12-beta.2-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.
