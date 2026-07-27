"""
Recorded Future API client for test assertions.

Uses:
- gw/azure-identity  — same endpoint as the Logic App (search + detail)
- playbook-alert/common  — public API for status lookup by ID
"""
import requests

from . import config

_SESSION = requests.Session()
_SESSION.headers.update({
    "X-RFToken": config.RF_TOKEN,
    "Content-Type": "application/json",
})

_GW_BASE = config.RF_GW_BASE
_PUBLIC_BASE = "https://api.recordedfuture.com/playbook-alert"


def get_new_pba_via_gateway() -> list[dict]:
    """
    Call the gateway search endpoint (exactly as the Logic App does) and
    return pba_items.  Passes max_lookback_days=21 to widen the window.
    """
    resp = _SESSION.post(
        f"{_GW_BASE}/playbook-alerts/search",
        json={"lookback_days": 21, "max_lookback_days": 21, "status": ["New"]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("pba_items", [])


def reset_alert_to_new(alert_id: str = config.TEST_ALERT_ID) -> None:
    """Set the test alert back to New so the next scenario can consume it."""
    resp = _SESSION.put(
        f"{_GW_BASE}/playbook-alerts/update",
        json={
            "alert_id": alert_id,
            "status": "New",
            "log_entry": "Reset to New by integration test runner",
        },
        timeout=30,
    )
    resp.raise_for_status()


def get_alert_status(alert_id: str = config.TEST_ALERT_ID) -> str:
    """Fetch current alert status via the public common endpoint."""
    resp = _SESSION.get(
        f"{_PUBLIC_BASE}/common/{alert_id}",
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    return data.get("status", "")
