from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.webui.routes.system import api_clear_runtime_logs, api_runtime_log_status


class FakeAPI:
    def __init__(self) -> None:
        self.cleared = False

    def runtime_log_status(self) -> dict:
        return {"ok": True, "retention_days": 30, "file_count": 1, "total_bytes": 12}

    def clear_runtime_logs(self) -> dict:
        self.cleared = True
        return {"ok": True, "retention_days": 30, "file_count": 0, "total_bytes": 0}


def _payload(response) -> dict:
    return json.loads(response.text)


@pytest.mark.asyncio
async def test_runtime_log_status_is_read_only():
    api = FakeAPI()
    response = await api_runtime_log_status(SimpleNamespace(app={"api": api}))
    assert response.status == 200
    assert _payload(response)["retention_days"] == 30
    assert api.cleared is False


@pytest.mark.asyncio
async def test_clear_runtime_logs_requires_explicit_confirmation():
    api = FakeAPI()
    denied = await api_clear_runtime_logs(SimpleNamespace(headers={}, app={"api": api}))
    assert denied.status == 403
    assert api.cleared is False

    confirmed = await api_clear_runtime_logs(
        SimpleNamespace(headers={"X-TRPG-Confirm": "true"}, app={"api": api})
    )
    assert confirmed.status == 200
    assert api.cleared is True
