"""DiceFrame Hub 的容错 HTTP 客户端。

所有 Hub 网络访问都收口在本模块：按场景限定超时、熔断、磁盘缓存和本地安装身份
不会泄漏到 Web 路由或插件宿主的业务代码中。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.parse import quote

import aiohttp

from src.version import __version__

logger = logging.getLogger("trpg.hub")

DEFAULT_HUB_URL = "https://api.diceframe.com"
# 商店目录缓存有效期：1 天（目录变动频繁，应尽快看到上架/更新）
_CATALOG_CACHE_MAX_AGE = 24 * 60 * 60
# 插件 README 等详情缓存有效期：1 天
_CACHE_MAX_AGE = 24 * 60 * 60
_FAILURE_THRESHOLD = 3
_BREAKER_SECONDS = 60
_EVENT_QUEUE_SIZE = 64
_HEARTBEAT_INTERVAL = 6 * 60 * 60
_READ_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
_INTERACTION_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
# 商店目录需要快速降级；用户主动打开的详情面板则允许慢链路有完整的加载时间。
_PLUGIN_DETAIL_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=5, sock_read=55)
_RENDEZVOUS_CONNECT_RETRY_DELAY = 0.2


class HubUnavailable(RuntimeError):
    """Hub 暂时不可用；调用方应使用本地缓存或原有镜像降级。"""


class HubConnectionUnavailable(HubUnavailable):
    """连接 Hub 失败；retry_safe 仅在请求尚未发送时为真。"""

    def __init__(self, *, retry_safe: bool = False) -> None:
        super().__init__("暂时无法连接 DiceFrame Hub，请检查网络后重试")
        self.retry_safe = bool(retry_safe)


class HubHTTPError(HubUnavailable):
    """Hub 返回了非 2xx；保留 status、Hub 的 detail 和 Retry-After，供路由透传。"""

    def __init__(
        self,
        status: int,
        *,
        detail: str = "",
        retry_after: str = "",
        error_code: str = "",
    ) -> None:
        self.status = status
        self.detail = detail
        self.retry_after = retry_after
        self.error_code = error_code
        message = f"DiceFrame Hub HTTP {status}"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


def _platform_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def _validated_base_url(value: str) -> str:
    candidate = (value or DEFAULT_HUB_URL).strip().rstrip("/")
    parsed = urlsplit(candidate)
    local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not local_http:
        raise ValueError("DiceFrame Hub 地址必须使用 HTTPS；仅本机开发地址允许 HTTP")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("DiceFrame Hub 地址无效")
    return candidate


class HubClient:
    """进程级 Hub 客户端；目录读取不创建安装身份，交互时才按需创建。"""

    def __init__(
        self,
        data_dir: Path,
        *,
        base_url: str | None = None,
        telemetry_enabled: bool = False,
        telemetry_choice_made: bool = False,
    ) -> None:
        configured_url = base_url or os.getenv("DICEFRAME_HUB_URL") or DEFAULT_HUB_URL
        self.base_url = _validated_base_url(configured_url)
        self.data_dir = data_dir / "hub"
        self.identity_file = self.data_dir / "identity.json"
        self.cache_file = self.data_dir / "cache.json"
        self.telemetry_enabled = bool(telemetry_enabled)
        self.telemetry_choice_made = bool(telemetry_choice_made)
        self._session: aiohttp.ClientSession | None = None
        self._event_queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(
            maxsize=_EVENT_QUEUE_SIZE
        )
        self._event_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._identity_lock = asyncio.Lock()
        self._failures = 0
        self._breaker_until = 0.0

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=_READ_TIMEOUT,
                headers={"User-Agent": f"DiceFrame/{__version__}"},
                raise_for_status=False,
            )
        if self._event_task is None or self._event_task.done():
            self._event_task = asyncio.create_task(self._event_worker(), name="diceframe-hub-events")
        self._refresh_heartbeat_task()

    async def close(self) -> None:
        for task in (self._heartbeat_task, self._event_task):
            if task is not None:
                task.cancel()
        for task in (self._heartbeat_task, self._event_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._heartbeat_task = None
        self._event_task = None
        if self._session is not None:
            await self._session.close()
        self._session = None

    async def catalog(self) -> dict[str, Any]:
        """读取完整 Hub 插件目录；失败时返回最多 30 天的本地缓存。"""
        started = time.monotonic()
        try:
            items: list[dict[str, Any]] = []
            page = 1
            while page <= 10:
                payload = await self._request(
                    "GET", f"/v1/plugins?page={page}&page_size=50&sort=name"
                )
                batch = payload.get("items") if isinstance(payload, dict) else None
                if not isinstance(batch, list):
                    raise HubUnavailable("Hub 插件目录响应无效")
                items.extend(item for item in batch if isinstance(item, dict))
                pages = int(payload.get("pages") or 0)
                if page >= pages:
                    break
                page += 1
            result = {
                "items": items,
                "fetched_at": time.time(),
                "source": {
                    "mirror_name": "DiceFrame Hub",
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "hub": True,
                    "stale": False,
                },
            }
            self._write_cache_entry("catalog", result)
            return {"ok": True, **result}
        except (HubUnavailable, aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            cached = self._read_cache_entry("catalog", _CATALOG_CACHE_MAX_AGE)
            if cached is not None:
                source = dict(cached.get("source") or {})
                source.update({
                    "hub": True,
                    "stale": True,
                    "error": str(exc),
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                })
                return {"ok": True, **cached, "source": source}
            return {"ok": False, "items": [], "error": str(exc)}

    async def plugin_detail(self, plugin_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/v1/plugins/{quote(plugin_id, safe='')}",
            auth_optional=True,
            request_timeout=_PLUGIN_DETAIL_TIMEOUT,
        )

    async def create_rendezvous_room(self, peer_count: int) -> dict[str, Any]:
        """Create a governed host-star room with the local pseudonymous identity."""
        if isinstance(peer_count, bool) or not isinstance(peer_count, int) or not 2 <= peer_count <= 32:
            raise ValueError("peer_count 必须是 2 到 32 的整数")
        payload: dict[str, Any] = {}
        for attempt in range(2):
            try:
                payload = await self._create_rendezvous_room_request(peer_count)
                break
            except HubConnectionUnavailable as exc:
                # ClientConnectorError 表示 TCP/TLS 连接尚未建立，请求没有发送；
                # 这种失败重试 POST 不会重复建房。已发送后断线/超时则不自动重试。
                if attempt or not exc.retry_safe:
                    raise
                await asyncio.sleep(_RENDEZVOUS_CONNECT_RETRY_DELAY)
        invitations = payload.get("invitations")
        required_strings = (
            "room_code",
            "host_peer_id",
            "host_token",
            "expires_at",
            "websocket_url",
        )
        valid_invitations = isinstance(invitations, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("peer_id"), str)
            and isinstance(item.get("token"), str)
            for item in invitations
        )
        protocol_version = payload.get("protocol_version")
        websocket_url = payload.get("websocket_url")
        if (
            (
                protocol_version != 2
                # v3+ 是 Hub 新增协议：应提示更新客户端，而不是误导用户更新 Hub。
                and not (isinstance(protocol_version, int) and protocol_version > 2)
            )
            or payload.get("topology") != "host-star"
            or any(not isinstance(payload.get(key), str) for key in required_strings)
            # 隐私政策承诺信令走 HTTPS/WSS：拒绝明文 ws 或任意非 websocket scheme。
            or not isinstance(websocket_url, str)
            or not (websocket_url.startswith("wss://") or websocket_url.startswith("ws://"))
            or not valid_invitations
            or len(invitations) != peer_count - 1
        ):
            raise HubUnavailable("Hub 联机协议不兼容或响应不完整，请先更新 Hub")
        if protocol_version != 2:
            raise HubUnavailable("Hub 已升级到更新的联机协议，请更新 DiceFrame 客户端")
        return payload

    async def _create_rendezvous_room_request(self, peer_count: int) -> dict[str, Any]:
        try:
            return await self._request(
                "POST",
                "/v1/rendezvous/rooms",
                auth=True,
                json_body={"peer_count": peer_count},
            )
        except HubHTTPError as exc:
            if exc.status != 401:
                raise
            # A locally cached identity may have been deleted by retention or a
            # previous clear-identity request. Re-register without deleting the
            # stored identity first: the old file is only overwritten after the
            # new registration succeeds, so a transient 401 (proxy hiccup, brief
            # Hub trouble) never destroys the installed identity and its
            # like/rating associations. A deliberate Hub revocation uses 403
            # and must never be bypassed this way.
            return await self._request(
                "POST",
                "/v1/rendezvous/rooms",
                auth=True,
                json_body={"peer_count": peer_count},
                force_reregister=True,
            )

    async def rendezvous_config(self) -> dict[str, Any]:
        """Read the anonymous Hub-side availability and entry visibility controls."""
        return await self._request("GET", "/v1/rendezvous/config")

    async def plugin_readme(self, plugin_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/v1/plugins/{quote(plugin_id, safe='')}/readme",
            request_timeout=_PLUGIN_DETAIL_TIMEOUT,
        )

    def readme_cache_path(self, plugin_id: str) -> Path:
        """README 磁盘缓存文件路径，键只含安全字符，避免路径注入。"""
        safe = re.sub(r"[^a-z0-9._-]+", "_", str(plugin_id or "").strip().lower())
        return self.data_dir / "readmes" / f"{safe}.json"

    def write_readme_cache(
        self,
        plugin_id: str,
        *,
        html: str,
        repository_url: str = "",
        commit_sha: str = "",
    ) -> None:
        """Hub 成功时把已清洗正文原子写入磁盘缓存，记录仓库与提交版本。"""
        self._atomic_write(
            self.readme_cache_path(plugin_id),
            {
                "html": html,
                "repository_url": repository_url,
                "commit_sha": commit_sha,
                "fetched_at": time.time(),
            },
        )

    def read_readme_cache(self, plugin_id: str) -> dict[str, Any] | None:
        """读取 README 磁盘缓存；超过 30 天视为失效。"""
        entry = self._read_json(self.readme_cache_path(plugin_id))
        if not isinstance(entry.get("html"), str):
            return None
        try:
            fetched_at = float(entry.get("fetched_at") or 0)
        except (TypeError, ValueError):
            return None
        if time.time() - fetched_at > _CACHE_MAX_AGE:
            return None
        return entry


    async def plugin_ratings(self, plugin_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/v1/plugins/{quote(plugin_id, safe='')}/ratings",
            request_timeout=_PLUGIN_DETAIL_TIMEOUT,
        )

    async def set_like(self, plugin_id: str, liked: bool) -> dict[str, Any]:
        method = "PUT" if liked else "DELETE"
        return await self._request(
            method, f"/v1/plugins/{quote(plugin_id, safe='')}/like", auth=True
        )

    async def set_rating(
        self, plugin_id: str, stars: int | None, tags: list[str] | None = None
    ) -> dict[str, Any]:
        if stars is None:
            return await self._request(
                "DELETE",
                f"/v1/plugins/{quote(plugin_id, safe='')}/rating",
                auth=True,
                empty_ok=True,
            )
        return await self._request(
            "PUT",
            f"/v1/plugins/{quote(plugin_id, safe='')}/rating",
            auth=True,
            json_body={"stars": stars, "tags": tags or []},
        )

    def queue_download_event(
        self,
        plugin_id: str,
        *,
        event_id: str,
        kind: str,
        plugin_version: str = "",
        artifact_hash: str = "",
    ) -> bool:
        payload = {
            "event_id": event_id,
            "kind": kind,
            "plugin_version": plugin_version,
            "artifact_hash": artifact_hash,
        }
        try:
            self._event_queue.put_nowait((plugin_id, payload))
            return True
        except asyncio.QueueFull:
            logger.debug("Hub 事件队列已满，丢弃 %s/%s", plugin_id, kind)
            return False

    async def set_telemetry(self, enabled: bool, *, choice_made: bool = True) -> None:
        self.telemetry_enabled = bool(enabled)
        self.telemetry_choice_made = bool(choice_made)
        # 本地选择立即生效；特别是关闭时，不能因 Hub 离线而继续心跳。
        self._refresh_heartbeat_task()
        identity = self._read_identity()
        if identity.get("installation_token"):
            try:
                await self._request(
                    "PATCH",
                    "/v1/installations/me",
                    auth=True,
                    json_body={"telemetry_enabled": self.telemetry_enabled},
                )
            except (HubUnavailable, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                logger.debug("Hub 离线，统计偏好仅在本机生效")

    async def delete_identity(self) -> None:
        identity = self._read_identity()
        if identity.get("installation_token"):
            await self._request("DELETE", "/v1/installations/me", auth=True, empty_ok=True)
        self.identity_file.unlink(missing_ok=True)

    async def _event_worker(self) -> None:
        while True:
            plugin_id, payload = await self._event_queue.get()
            try:
                await self._request(
                    "POST",
                    f"/v1/plugins/{quote(plugin_id, safe='')}/download-events",
                    auth=True,
                    json_body=payload,
                )
            except (HubUnavailable, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                logger.debug("Hub 下载事件发送失败：%s/%s", plugin_id, payload.get("kind"))
            finally:
                self._event_queue.task_done()

    def _refresh_heartbeat_task(self) -> None:
        should_run = self.telemetry_choice_made and self.telemetry_enabled and self._session is not None
        if should_run and (self._heartbeat_task is None or self._heartbeat_task.done()):
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(), name="diceframe-hub-heartbeat"
            )
        elif not should_run and self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await self._request(
                    "POST",
                    "/v1/telemetry/heartbeat",
                    auth=True,
                    json_body={
                        "schema_version": 1,
                        "app_version": __version__,
                        "platform": _platform_name(),
                    },
                )
            except (HubUnavailable, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                logger.debug("Hub 匿名心跳发送失败")
            await asyncio.sleep(_HEARTBEAT_INTERVAL)

    async def _ensure_identity(self, *, force_reregister: bool = False) -> str:
        current = self._read_identity()
        token = str(current.get("installation_token") or "")
        if token and not force_reregister:
            return token
        async with self._identity_lock:
            current = self._read_identity()
            token = str(current.get("installation_token") or "")
            if token and not force_reregister:
                return token
            payload = await self._request(
                "POST",
                "/v1/installations",
                json_body={
                    "app_version": __version__,
                    "platform": _platform_name(),
                    "telemetry_enabled": self.telemetry_choice_made and self.telemetry_enabled,
                },
            )
            token = str(payload.get("installation_token") or "")
            installation_id = str(payload.get("installation_id") or "")
            if not token or not installation_id:
                raise HubUnavailable("Hub 安装身份响应无效")
            # 401 轮换场景：注册成功即证明旧 token 已被 Hub 收回，
            # 此时才落盘覆盖；注册失败则原身份文件保持不动。
            self._atomic_write(
                self.identity_file,
                {"installation_id": installation_id, "installation_token": token},
            )
            return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = False,
        auth_optional: bool = False,
        force_reregister: bool = False,
        json_body: dict[str, Any] | None = None,
        empty_ok: bool = False,
        request_timeout: aiohttp.ClientTimeout | None = None,
    ) -> dict[str, Any]:
        if time.monotonic() < self._breaker_until:
            remaining = max(1, int(self._breaker_until - time.monotonic()) + 1)
            raise HubUnavailable(
                f"DiceFrame Hub 连续请求失败，已临时熔断（约 {remaining} 秒后可重试）"
            )
        if self._session is None or self._session.closed:
            await self.start()
        assert self._session is not None
        headers: dict[str, str] = {}
        if auth:
            headers["Authorization"] = f"Bearer {await self._ensure_identity(force_reregister=force_reregister)}"
        elif auth_optional:
            token = str(self._read_identity().get("installation_token") or "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        try:
            timeout = request_timeout or (
                _READ_TIMEOUT if method.upper() in {"GET", "HEAD"} else _INTERACTION_TIMEOUT
            )
            async with self._session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=json_body,
                timeout=timeout,
            ) as response:
                if response.status < 200 or response.status >= 300:
                    # Hub 的失败响应体里带用户可读的 detail（如"需要先安装""冷却中"），
                    # 读取并随异常透传，路由层再转成前端展示的文案。
                    detail = ""
                    error_code = ""
                    try:
                        error_body = await response.json(content_type=None)
                        if isinstance(error_body, dict):
                            detail = str(error_body.get("detail") or "")
                            error_code = str(error_body.get("code") or "")[:80]
                    except (ValueError, aiohttp.ClientError):
                        pass
                    raise HubHTTPError(
                        response.status,
                        detail=detail,
                        retry_after=response.headers.get("Retry-After", ""),
                        error_code=error_code,
                    )
                if response.status == 204 or empty_ok and response.content_length == 0:
                    payload: dict[str, Any] = {}
                else:
                    decoded = await response.json(content_type=None)
                    if not isinstance(decoded, dict):
                        raise HubUnavailable("DiceFrame Hub 响应格式无效")
                    payload = decoded
        except asyncio.CancelledError:
            raise
        except HubHTTPError as exc:
            if exc.status >= 500:
                self._record_failure()
            raise
        except asyncio.TimeoutError as exc:
            self._record_failure()
            raise HubConnectionUnavailable(retry_safe=False) from exc
        except aiohttp.ClientConnectorError as exc:
            self._record_failure()
            raise HubConnectionUnavailable(retry_safe=True) from exc
        except aiohttp.ClientError as exc:
            self._record_failure()
            raise HubConnectionUnavailable(retry_safe=False) from exc
        except (HubUnavailable, ValueError):
            self._record_failure()
            raise
        self._failures = 0
        self._breaker_until = 0.0
        return payload

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= _FAILURE_THRESHOLD:
            self._breaker_until = time.monotonic() + _BREAKER_SECONDS

    def _read_identity(self) -> dict[str, Any]:
        return self._read_json(self.identity_file)

    def _read_cache_entry(self, key: str, max_age: float = _CACHE_MAX_AGE) -> dict[str, Any] | None:
        entry = self._read_json(self.cache_file).get(key)
        if not isinstance(entry, dict):
            return None
        try:
            fetched_at = float(entry.get("fetched_at") or 0)
        except (TypeError, ValueError):
            return None
        if time.time() - fetched_at > max_age:
            return None
        return entry

    def _write_cache_entry(self, key: str, value: dict[str, Any]) -> None:
        cache = self._read_json(self.cache_file)
        cache[key] = value
        self._atomic_write(self.cache_file, cache)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def _atomic_write(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
        try:
            temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            if os.name != "nt":
                temp.chmod(0o600)
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
