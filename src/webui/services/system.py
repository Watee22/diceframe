"""System metadata and update checks."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp

from src.version import DEFAULT_UPDATE_REPOSITORY, __version__
from src.runtime_logging import clear_runtime_logs as clear_logs
from src.runtime_logging import runtime_log_status as log_status

if TYPE_CHECKING:
    from src.webui.api import WebAPI

logger = logging.getLogger("trpg")

GITHUB_API = "https://api.github.com"
_VERSION_RE = re.compile(
    r"^\s*[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\s*$"
)


class NoReleaseError(RuntimeError):
    """Raised when the repository exists but has no public releases yet."""


def _data_dir(api: "WebAPI") -> Path:
    return api._reg.save_dir.parent


def runtime_log_status(api: "WebAPI") -> dict[str, Any]:
    return log_status(_data_dir(api))


def clear_runtime_logs(api: "WebAPI") -> dict[str, Any]:
    return clear_logs(_data_dir(api))


def _parse_version(value: str) -> tuple[tuple[int, int, int], tuple[str, ...] | None] | None:
    match = _VERSION_RE.match(value or "")
    if not match:
        return None
    major, minor, patch, prerelease = match.groups()
    return (
        (int(major), int(minor or 0), int(patch or 0)),
        tuple(prerelease.split(".")) if prerelease else None,
    )


def _compare_prerelease(left: tuple[str, ...] | None, right: tuple[str, ...] | None) -> int:
    if left is None or right is None:
        if left is right:
            return 0
        return 1 if left is None else -1
    for left_part, right_part in zip(left, right):
        if left_part == right_part:
            continue
        left_numeric = left_part.isdigit()
        right_numeric = right_part.isdigit()
        if left_numeric and right_numeric:
            return 1 if int(left_part) > int(right_part) else -1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return 1 if left_part > right_part else -1
    return (len(left) > len(right)) - (len(left) < len(right))


def is_newer_version(latest: str, current: str) -> bool:
    latest_version = _parse_version(latest)
    current_version = _parse_version(current)
    if latest_version is None or current_version is None:
        return False
    latest_core, latest_prerelease = latest_version
    current_core, current_prerelease = current_version
    if latest_core != current_core:
        return latest_core > current_core
    return _compare_prerelease(latest_prerelease, current_prerelease) > 0


async def check_updates(api: "WebAPI", include_prerelease: bool | None = None) -> dict[str, Any]:
    repo = str(os.getenv("TRPG_UPDATE_REPOSITORY") or DEFAULT_UPDATE_REPOSITORY).strip()
    if not repo or "/" not in repo:
        return {
            "ok": False,
            "error": "更新仓库配置无效",
            "current_version": __version__,
            "repository": repo,
            "update_available": False,
        }

    if include_prerelease is None:
        config_state = getattr(api, "_config_state", None) or {}
        include_prerelease = str(config_state.get("update_channel") or "stable") == "preview"
    channel = "preview" if include_prerelease else "stable"

    check_source: dict[str, Any] = {"mode": "github-api", "mirror_name": "GitHub API"}
    try:
        proxy_url = str(getattr(getattr(api, "_llm_client", None), "proxy_url", "") or "")
        release, check_source = await _fetch_release_for_api(api, repo, include_prerelease, proxy_url)
    except NoReleaseError as exc:
        return {
            "ok": True,
            "message": str(exc),
            "current_version": __version__,
            "repository": repo,
            "update_available": False,
            "no_release": True,
            "channel": channel,
            "releases_url": f"https://github.com/{repo}/releases",
            "source_url": f"https://github.com/{repo}",
            "install_hint": _install_hint(repo),
            "check_source": check_source,
        }
    except Exception as exc:
        logger.warning("检查更新失败: %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "current_version": __version__,
            "repository": repo,
            "update_available": False,
        }

    latest_version = str(release.get("tag_name") or "").lstrip("vV")
    latest = {
        "version": latest_version,
        "tag_name": release.get("tag_name", ""),
        "name": release.get("name", ""),
        "body": release.get("body", ""),
        "html_url": release.get("html_url", f"https://github.com/{repo}/releases"),
        "published_at": release.get("published_at", ""),
        "prerelease": bool(release.get("prerelease")),
        "assets": [
            {
                "name": asset.get("name", ""),
                "download_url": asset.get("browser_download_url", ""),
                "size": asset.get("size", 0),
            }
            for asset in release.get("assets", [])
            if isinstance(asset, dict)
        ],
    }
    return {
        "ok": True,
        "current_version": __version__,
        "repository": repo,
        "update_available": is_newer_version(latest_version, __version__),
        "no_release": False,
        "channel": channel,
        "latest": latest,
        "release_url": latest["html_url"],
        "releases_url": f"https://github.com/{repo}/releases",
        "source_url": f"https://github.com/{repo}",
        "install_hint": _install_hint(repo),
        "check_source": check_source,
    }


async def _fetch_release(repo: str, include_prerelease: bool, proxy_url: str = "") -> dict[str, Any]:
    endpoint = f"{GITHUB_API}/repos/{repo}/releases"
    if not include_prerelease:
        endpoint += "/latest"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "DiceFrame update checker",
    }
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        request_kwargs = {"proxy": proxy_url} if proxy_url else {}
        async with session.get(endpoint, **request_kwargs) as resp:
            data = await resp.json(content_type=None)
            if resp.status == 404:
                raise NoReleaseError("暂无公开 Release")
            if resp.status >= 400:
                message = data.get("message") if isinstance(data, dict) else await resp.text()
                raise RuntimeError(f"GitHub 返回 HTTP {resp.status}: {message}")
            if not include_prerelease:
                return data
            if not isinstance(data, list):
                raise RuntimeError("GitHub Release 返回格式异常")
            for release in data:
                if isinstance(release, dict) and not release.get("draft"):
                    return release
    raise RuntimeError("没有可用的 Release")


async def _fetch_release_for_api(
    api: "WebAPI",
    repo: str,
    include_prerelease: bool,
    proxy_url: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    plugin_host = getattr(api, "_plugins", None)
    mirrors = getattr(plugin_host, "mirrors", None)
    api_path = f"/repos/{repo}/releases"
    if not include_prerelease:
        api_path += "/latest"
    if mirrors is not None:
        result = await mirrors.fetch_github_api(api_path, official_first=True)
        if result.ok and isinstance(result.data, str):
            try:
                data = await _parse_release_payload(result.data, include_prerelease)
                source = result.to_dict()
                source.pop("data", None)
                return data, {"mode": "mirror", **source}
            except Exception as exc:
                logger.warning("镜像源返回的 Release 数据无法解析，回退 GitHub API：%s", exc)
        logger.warning("通过镜像源检查更新失败，回退 GitHub API：%s", result.error)
    release = await _fetch_release(repo, include_prerelease, proxy_url)
    return release, {"mode": "github-api", "mirror_name": "GitHub API"}


async def _parse_release_payload(payload: str, include_prerelease: bool) -> dict[str, Any]:
    import json

    data = json.loads(payload)
    if isinstance(data, dict) and data.get("message") == "Not Found":
        raise NoReleaseError("暂无公开 Release")
    if not include_prerelease:
        if not isinstance(data, dict):
            raise RuntimeError("GitHub Release 返回格式异常")
        return data
    if not isinstance(data, list):
        raise RuntimeError("GitHub Release 返回格式异常")
    for release in data:
        if isinstance(release, dict) and not release.get("draft"):
            return release
    raise RuntimeError("没有可用的 Release")


def _install_hint(repo: str) -> dict[str, str]:
    return {
        "windows": "下载新版源码包或 Release 附件，保留 data/ 目录后替换程序文件，再重新运行 web_ui.bat。",
        "docker": "Compose 部署请先进入存放 docker-compose.yml 的目录，再拉取镜像并重新 docker compose up -d；docker run 部署需重新创建容器，源码镜像需用新版源码重新 build。",
        "source": f"源码用户可从 https://github.com/{repo}/releases 下载新版，升级前先备份 data/。",
    }
