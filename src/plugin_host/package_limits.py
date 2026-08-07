"""Resource budgets for untrusted plugin packages."""

# 上限放宽（2026-08-08）：支持商店分发带二进制的大插件（如 cloudflared ~54MB）。
# zip 包上限容纳 54MB 二进制 + 其余源码；单文件上限对应解压后的二进制体积。
MAX_PLUGIN_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_PLUGIN_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_PLUGIN_FILE_BYTES = 80 * 1024 * 1024
MAX_PLUGIN_ARCHIVE_FILES = 2048
MAX_PLUGIN_PATH_CHARS = 240
