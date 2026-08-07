"""父进程存活监控（cloudflare-tunnel 插件内部实现）。

宿主为进程型插件注入 ``TRPG_PARENT_PID``（主进程 PID）。插件监控父进程存活：
宿主退出后立即触发清理（kill cloudflared 子进程）并退出，避免僵尸与残留。

注：这是本插件的内部工具，不从 SDK 公共面导出。未来若有第二个进程型插件需要，
再提炼回 src/plugin_sdk。
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

logger = logging.getLogger("trpg.cloudflare_tunnel")


def pid_exists(pid: int) -> bool:
    """跨平台判断 PID 是否存活（Windows tasklist / POSIX kill(pid,0)）。"""
    if pid <= 0 or pid == os.getpid():
        return False
    if os.name == "nt":
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            return str(pid) in output
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_parent_watch(
    *,
    on_exit: object | None = None,
    interval_sec: float = 2.0,
) -> threading.Thread:
    """启动父进程监控线程：宿主进程消失时执行 ``on_exit()`` 并退出插件。"""
    parent_pid = int(os.environ.get("TRPG_PARENT_PID", "0") or 0)
    if parent_pid <= 0:
        return _noop_thread()

    def _watch() -> None:
        while True:
            time.sleep(interval_sec)
            if not pid_exists(parent_pid):
                logger.warning("检测到 DiceFrame 主进程已退出，插件自动停止: parent_pid=%s", parent_pid)
                if callable(on_exit):
                    try:
                        on_exit()
                    except Exception:  # noqa: BLE001
                        logger.exception("父进程退出清理回调失败")
                break

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return thread


def _noop_thread() -> threading.Thread:
    thread = threading.Thread(target=lambda: None, daemon=True)
    thread.start()
    return thread
