# Starter Content 示例内容包

中文 | [English](README_EN.md)

这是 DiceFrame 的内容包示例插件，演示 `content-pack` 如何贡献规则、世界模板、角色模板、NPC、道具、法术和职业。

## 打包

```powershell
python scripts\package_plugin.py plugins\examples\starter-content --overwrite
```

生成的 zip 位于 `dist/plugins/`，可以在 WebUI 的“设置 -> 插件 -> 安装插件”里安装。

## 当前效果

- 规则会出现在规则列表。
- 示例规则显式声明 d20 总值检定、自然 20/1 与优势/劣势；内容作者可直接复制后按需修改。
- 世界模板会出现在创建游戏的世界模板列表。
- 角色模板可从插件设置页导入角色卡库。
- NPC、道具、法术、职业可从插件设置页导入指定世界书。

此示例不启动后台进程，也不访问外部网络。

发布内容包前可运行规则审计和短程长团模拟：

```powershell
python scripts\audit_rules.py --strict --path plugins\examples\starter-content
python scripts\audit_dice_campaigns.py --rounds 25 --players 6 --rule-path plugins\examples\starter-content --rule example_rule
```
