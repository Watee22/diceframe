"""Cloudflare 快速隧道插件：一键生成公网 HTTPS 访问地址并上报核心。

流程：下载/校验 cloudflared 二进制 -> spawn `tunnel --url $TRPG_API_BASE` ->
解析 stdout 里的 https://*.trycloudflare.com -> POST /api/bot/tunnel/publish 上报。
停止时 kill 子进程 -> POST /release 恢复 public_base_url。

进程管理：
- 宿主 PluginHost 负责重启本插件进程；本插件负责自己 spawn 的 cloudflared 子进程。
- 后台线程监控 TRPG_PARENT_PID：宿主进程退出则本插件立即清理 cloudflared 并退出。
- cloudflared 崩溃时自动重启（指数退避 1s->30s，连续 5 次进 error 停止重试）。
- publish 失败不 kill 隧道（避免死循环）；核心不支持时降级手动模式（§10）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from src.plugin_sdk import ToolRuntime
from parent_watch import start_parent_watch

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("trpg.cloudflare_tunnel")

runtime = ToolRuntime()

PLUGIN_DIR = Path(__file__).resolve().parent
BIN_DIR = Path(os.environ.get("DICEFRAME_PLUGIN_DATA_DIR", "") or (PLUGIN_DIR / "runtime")) / "bin"
BIN_NAME = "cloudflared.exe" if os.name == "nt" else "cloudflared"
BIN_PATH = BIN_DIR / BIN_NAME
# 隧道 URL：排除 api.trycloudflare.com（cloudflared 注册端点），只匹配随机子域隧道地址
URL_RE = re.compile(r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com")
START_TIMEOUT_SEC = 60.0

# cloudflared 版本 pin（windows-amd64 / linux-amd64）
CLOUDFLARED_VERSION = "2026.7.3"
# 下载校验：填入对应版本 sha256 后启用；为空则仅记录警告（二进制优先用随包分发的内置版本）。
CLOUDFLARED_SHA256: dict[str, str] = {
    # "windows-amd64": "...",
    # "linux-amd64": "...",
}

# 内置二进制：构建时打进主程序包的 cloudflared/ 目录（见 scripts/build_release.py）。
_BUILTIN_BIN_DIR = Path(os.environ.get("DICEFRAME_APP_ROOT", "")) / "cloudflared" if os.environ.get("DICEFRAME_APP_ROOT") else PLUGIN_DIR.parent.parent.parent / "cloudflared"

_lock = threading.Lock()
_process: subprocess.Popen | None = None
_current_url = ""
_started_at = 0.0
_stop_event = threading.Event()
# 是否应运行隧道（显式 start/auto_start 置 True，stop/连续失败置 False）。monitor 仅在 True 时重启。
_should_run = False
# 发布模式："auto"(核心已写入) | "manual"(核心不支持，需手动填) | ""(未发布/发布失败)
_mode = ""
_fail_count = 0   # cloudflared 连续启动失败次数
_exit_count = 0   # cloudflared 进程退出总次数
_error = ""       # 连续失败 5 次后的错误状态


def _os_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "windows-amd64" if os.name == "nt" else "linux-amd64"
    raise RuntimeError("当前平台不支持 cloudflared")


def _download_binary() -> str:
    # 优先用数据目录手放的二进制（离线/企业环境手动覆盖），其次随包分发的内置二进制，最后在线下载。
    if BIN_PATH.exists():
        return str(BIN_PATH)
    builtin = _BUILTIN_BIN_DIR / BIN_NAME
    if builtin.exists():
        return str(builtin)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    asset = _os_arch()
    if asset == "windows-amd64":
        url = (f"https://github.com/cloudflare/cloudflared/releases/download/"
               f"{CLOUDFLARED_VERSION}/cloudflared-windows-amd64.exe")
    else:
        url = (f"https://github.com/cloudflare/cloudflared/releases/download/"
               f"{CLOUDFLARED_VERSION}/cloudflared-linux-amd64")
    tmp = BIN_DIR / (BIN_NAME + ".tmp")
    last_error: Exception | None = None
    for _ in range(3):
        try:
            urllib.request.urlretrieve(url, tmp)
            os.replace(tmp, BIN_PATH)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2)
    else:
        raise RuntimeError(f"cloudflared 下载失败: {last_error}")
    expected = CLOUDFLARED_SHA256.get(asset)
    if expected:
        actual = hashlib.sha256(BIN_PATH.read_bytes()).hexdigest()
        if actual.lower() != expected.lower():
            BIN_PATH.unlink(missing_ok=True)
            raise RuntimeError(f"cloudflared sha256 校验失败: 期望 {expected} 实际 {actual}")
    else:
        logger.warning("未配置 cloudflared %s 的 sha256，跳过下载校验", asset)
    return str(BIN_PATH)


def _publish(url: str) -> dict:
    """上报 URL。核心不支持(404/403)时返回 manual 模式，其他错误抛异常。"""
    api_base = os.environ.get("TRPG_API_BASE", "").rstrip("/")
    token = os.environ.get("TRPG_BOT_TOKEN", "")
    if not api_base or not token:
        raise RuntimeError("宿主未注入 TRPG_API_BASE / TRPG_BOT_TOKEN")
    req = urllib.request.Request(
        f"{api_base}/api/bot/tunnel/publish",
        data=json.dumps({"url": url}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Bot-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 403):
            # 旧版核心无此端点 / 权限不识别 -> 手动模式（§10 降级）
            return {"ok": True, "url": url, "mode": "manual",
                    "hint": "当前核心版本不支持自动写入，请将上述地址填入设置的公开访问地址"}
        raise RuntimeError(f"发布失败: HTTP {exc.code} {exc.reason}")
    if not body.get("ok"):
        raise RuntimeError(str(body.get("error") or "发布失败"))
    body["mode"] = "auto"
    return body


def _publish_with_retry(url: str) -> dict:
    """发布；连接级错误（核心未就绪等）重试 3 次，HTTP 业务错误立即抛出。"""
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            return _publish(url)
        except urllib.error.URLError as exc:
            last_exc = exc
            logger.warning("发布连接失败，重试: %s", exc)
            time.sleep(2.0)
    raise RuntimeError(f"发布连接失败: {last_exc}")


def _release() -> None:
    api_base = os.environ.get("TRPG_API_BASE", "").rstrip("/")
    token = os.environ.get("TRPG_BOT_TOKEN", "")
    if not api_base or not token:
        return
    try:
        req = urllib.request.Request(
            f"{api_base}/api/bot/tunnel/release",
            data=b"{}",
            headers={"Content-Type": "application/json", "X-Bot-Token": token},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=15)
        logger.info("隧道已 release")
    except Exception as exc:  # noqa: BLE001
        logger.warning("隧道 release 失败: %s", exc)


def _spawn(binary: str) -> subprocess.Popen:
    target = os.environ.get("TRPG_API_BASE", "http://127.0.0.1:18000")
    return subprocess.Popen(
        [binary, "tunnel", "--url", target, "--no-autoupdate", "--loglevel", "info"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _wait_url(proc: subprocess.Popen, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    buf = ""
    assert proc.stdout is not None
    while time.monotonic() < deadline:
        if _stop_event.is_set():
            raise RuntimeError("隧道停止")
        chunk = proc.stdout.readline()
        if not chunk:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
            continue
        buf += chunk
        match = URL_RE.search(buf)
        if match:
            return match.group(0)
    raise RuntimeError(f"未在 {timeout:.0f}s 内获得隧道地址")


def _start_tunnel_locked() -> None:
    """在锁内启动 cloudflared 并发布。

    cloudflared 起不来/拿不到 URL -> 清理子进程并抛异常（让 monitor 退避重试）。
    拿到 URL 后发布失败 -> 不 kill 隧道（避免死循环），仅记 _mode="" 未发布。
    """
    global _process, _current_url, _started_at, _mode, _fail_count
    if _process and _process.poll() is None:
        return
    binary = _download_binary()
    proc = _spawn(binary)
    _process = proc
    try:
        url = _wait_url(proc, START_TIMEOUT_SEC)
    except Exception:
        _kill_process_locked()
        raise
    _current_url = url
    _started_at = time.time()
    _fail_count = 0
    logger.info("已获得隧道地址: %s", url)
    try:
        result = _publish_with_retry(url)
        _mode = str(result.get("mode") or "")
        if _mode == "manual":
            logger.warning("核心不支持自动写入，切换手动模式: %s", result.get("hint", ""))
        else:
            logger.info("隧道已发布(auto): %s", url)
    except Exception as exc:  # noqa: BLE001
        _mode = ""
        logger.error("隧道发布失败，子进程保持运行（地址可手动复制）: %s", exc)


def _kill_process_locked() -> None:
    global _process, _current_url, _mode
    if _process and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
    _process = None
    if _current_url and _mode == "auto":
        _release()
    _current_url = ""
    _mode = ""


def _monitor_cloudflared() -> None:
    """后台线程：cloudflared 崩溃则自动重启（指数退避 1s->30s，连续 5 次进 error）。

    仅在 _should_run=True 时重启。父进程存活监控由 start_parent_watch 负责。
    """
    global _fail_count, _exit_count, _error, _should_run
    backoff = 1.0
    while not _stop_event.is_set():
        time.sleep(1.0)
        if not _should_run:
            continue
        with _lock:
            dead = _process is None or _process.poll() is not None
            if dead:
                _exit_count += 1
                _fail_count += 1
                if _fail_count > 5:
                    _error = f"cloudflared 连续启动失败 {_fail_count} 次，已停止重试"
                    _should_run = False
                    logger.error(_error)
                    continue
        if not dead:
            backoff = 1.0
            continue
        logger.warning("cloudflared 退出，%0.1fs 后重启（第 %d 次）", backoff, _fail_count)
        time.sleep(backoff)
        backoff = min(backoff * 2, 30.0)
        try:
            with _lock:
                _start_tunnel_locked()
        except Exception as exc:  # noqa: BLE001
            logger.error("cloudflared 重启失败: %s", exc)
    with _lock:
        _kill_process_locked()


@runtime.tool(
    name="tunnel_start",
    title="开启外网隧道",
    description="启动 cloudflared 快速隧道，生成公网 HTTPS 地址并写入邀请链接。",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
def tunnel_start(arguments: dict, context: dict) -> dict:
    global _should_run, _fail_count, _error
    with _lock:
        _should_run = True
        _fail_count = 0
        _error = ""
        if _process and _process.poll() is None:
            return {"ok": True, "url": _current_url, "running": True, "mode": _mode}
        try:
            _start_tunnel_locked()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
    return {"ok": True, "url": _current_url, "running": True, "mode": _mode}


@runtime.tool(
    name="tunnel_stop",
    title="停止外网隧道",
    description="停止隧道并恢复发布前的访问地址。",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
def tunnel_stop(arguments: dict, context: dict) -> dict:
    global _should_run
    _should_run = False
    with _lock:
        _kill_process_locked()
    return {"ok": True, "running": False, "url": ""}


@runtime.tool(
    name="tunnel_status",
    title="隧道状态",
    description="查看隧道运行状态与当前公网地址。",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
def tunnel_status(arguments: dict, context: dict) -> dict:
    with _lock:
        running = bool(_process and _process.poll() is None)
        return {
            "ok": True,
            "running": running,
            "url": _current_url,
            "started_at": _started_at,
            "mode": _mode,
            "error": _error,
            "exit_count": _exit_count,
            "binary_version": CLOUDFLARED_VERSION,
        }


if __name__ == "__main__":
    monitor = threading.Thread(target=_monitor_cloudflared, daemon=True)
    monitor.start()
    # 父进程消失时立即清理 cloudflared 并退出，避免僵尸与残留。
    start_parent_watch(on_exit=lambda: _stop_event.set())
    # 随宿主启动自动开隧道：放后台线程，避免阻塞 JSON-RPC initialize 握手。
    if os.environ.get("TUNNEL_AUTO_START", "").strip().lower() in {"1", "true", "yes"}:
        def _auto_start() -> None:
            global _should_run, _fail_count, _error
            _should_run = True
            _fail_count = 0
            _error = ""
            try:
                with _lock:
                    _start_tunnel_locked()
            except Exception as exc:  # noqa: BLE001
                logger.error("自动启动隧道失败: %s", exc)
        threading.Thread(target=_auto_start, daemon=True).start()
    try:
        runtime.run()
    finally:
        _stop_event.set()
        _should_run = False
        with _lock:
            _kill_process_locked()
