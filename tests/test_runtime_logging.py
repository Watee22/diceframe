from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from src.runtime_logging import (
    LOG_FILENAME,
    RETENTION_DAYS,
    cleanup_expired_runtime_logs,
    clear_runtime_logs,
    configure_runtime_logging,
    resolve_runtime_log_dir,
    runtime_log_status,
)


def test_resolve_log_dir_for_portable_and_docker(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("TRPG_LOG_DIR", raising=False)
    monkeypatch.setenv("TRPG_INSTALL_ROOT", str(tmp_path / "portable"))
    monkeypatch.setenv("TRPG_INSTALL_MODE", "portable")
    assert resolve_runtime_log_dir(tmp_path / "data") == (tmp_path / "portable" / "logs").resolve()

    monkeypatch.delenv("TRPG_INSTALL_ROOT")
    monkeypatch.setenv("TRPG_INSTALL_MODE", "docker-managed")
    assert resolve_runtime_log_dir(tmp_path / "data") == (tmp_path / "data" / "logs").resolve()


def test_runtime_logger_keeps_console_and_writes_file(tmp_path: Path):
    logger = logging.getLogger("test.runtime.logging")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    console = logging.StreamHandler()
    logger.addHandler(console)

    path = configure_runtime_logging(tmp_path / "data", logger=logger, log_dir=tmp_path / "logs")
    configure_runtime_logging(tmp_path / "data", logger=logger, log_dir=tmp_path / "logs")
    logger.info("runtime-log-probe")
    for handler in logger.handlers:
        handler.flush()

    assert console in logger.handlers
    assert len(logger.handlers) == 2
    assert "runtime-log-probe" in path.read_text(encoding="utf-8")
    result = clear_runtime_logs(tmp_path / "data", logger=logger, log_dir=tmp_path / "logs")
    assert result["cleared_bytes"] > 0
    assert path.read_text(encoding="utf-8") == ""
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()


def test_cleanup_and_manual_clear_only_touch_diceframe_logs(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old = log_dir / f"{LOG_FILENAME}.2026-01-01"
    recent = log_dir / f"{LOG_FILENAME}.2026-08-26"
    unrelated = log_dir / "plugin.log"
    for path in (old, recent, unrelated):
        path.write_text(path.name, encoding="utf-8")
    now = time.time()
    os.utime(old, (now - (RETENTION_DAYS + 1) * 86400,) * 2)

    assert cleanup_expired_runtime_logs(log_dir, now=now) == 1
    assert not old.exists()
    assert recent.exists()
    assert unrelated.exists()

    active = log_dir / LOG_FILENAME
    active.write_text("active", encoding="utf-8")
    result = clear_runtime_logs(tmp_path / "data", log_dir=log_dir)
    assert result["cleared_files"] == 2
    assert result["file_count"] == 0
    assert not active.exists()
    assert not recent.exists()
    assert unrelated.exists()


def test_runtime_log_status_does_not_expose_local_path(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / LOG_FILENAME).write_bytes(b"1234")
    status = runtime_log_status(tmp_path / "data", log_dir=log_dir)
    assert status == {
        "ok": True,
        "retention_days": RETENTION_DAYS,
        "file_count": 1,
        "total_bytes": 4,
    }
