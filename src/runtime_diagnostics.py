"""Bounded and redacted runtime-log context for DF Assistant."""

from __future__ import annotations

import re
from pathlib import Path

from src.runtime_logging import LOG_FILENAME, resolve_runtime_log_dir

MAX_LOG_FILES = 2
MAX_READ_BYTES = 256 * 1024
MAX_CONTEXT_CHARS = 24_000

_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(\b(?:api[_ -]?key|authorization|(?:api|access|bot|refresh|session)[_ -]?token|"
    r"token|password|secret|client[_ -]?secret|private[_ -]?key|cookie)\b"
    r"[\s\"']*[:=][\s\"']*)([^\s,;\"'&}]+)"
)
_BEARER_RE = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|password|secret)=)[^&\s]+"
)
_URL_USERINFO_RE = re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@")
_COMMON_TOKEN_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"hf_[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,})\b"
)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_SUCCESS_ACCESS_RE = re.compile(
    r'"(?:GET|HEAD|OPTIONS)\s+/api/[^\"]*\s+HTTP/\d(?:\.\d)?"\s+2\d\d\s',
    flags=re.IGNORECASE,
)
_VOLATILE_PREFIX_RE = re.compile(
    r"^\s*(?:\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\s*)?"
)


def redact_runtime_log_text(text: str) -> str:
    """Mask credentials while retaining diagnostic context."""
    redacted = _SENSITIVE_VALUE_RE.sub(r"\1[REDACTED]", text)
    redacted = _BEARER_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _QUERY_SECRET_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _URL_USERINFO_RE.sub(r"\1[REDACTED]@", redacted)
    redacted = _COMMON_TOKEN_RE.sub("[REDACTED]", redacted)
    return _JWT_RE.sub("[REDACTED]", redacted)


def _runtime_log_files(log_dir: Path) -> list[Path]:
    if not log_dir.exists():
        return []
    candidates = [
        path
        for path in log_dir.iterdir()
        if path.is_file()
        and (path.name == LOG_FILENAME or path.name.startswith(f"{LOG_FILENAME}."))
    ]
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[:MAX_LOG_FILES]


def _read_tail(path: Path, byte_limit: int) -> str:
    with path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - byte_limit))
        return stream.read(byte_limit).decode("utf-8", errors="replace")


def _compact_log_text(text: str) -> str:
    """Drop routine successful polling and collapse repeated adjacent events."""
    output: list[str] = []
    previous = ""
    repeated = 0
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if _SUCCESS_ACCESS_RE.search(line):
            continue
        normalized = re.sub(r"\d+", "#", _VOLATILE_PREFIX_RE.sub("", line).lower())
        if normalized and normalized == previous:
            repeated += 1
            continue
        if repeated:
            output.append(f"[previous event repeated {repeated} times]")
            repeated = 0
        output.append(line)
        previous = normalized
    if repeated:
        output.append(f"[previous event repeated {repeated} times]")
    return "\n".join(output)


def assistant_runtime_log_context(data_dir: Path) -> tuple[str, int]:
    """Return recent redacted log context and the number of source files."""
    files = _runtime_log_files(resolve_runtime_log_dir(data_dir))
    if not files:
        return "", 0
    per_file = max(1, MAX_READ_BYTES // len(files))
    raw = "\n".join(_read_tail(path, per_file) for path in reversed(files))
    compact = _compact_log_text(redact_runtime_log_text(raw))
    compact = compact.replace("<runtime-log-data>", "[runtime-log-data]")
    compact = compact.replace("</runtime-log-data>", "[/runtime-log-data]")
    return compact[-MAX_CONTEXT_CHARS:], len(files)
