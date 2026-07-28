"""
Recorded Future API client for test assertions.

Uses:
- gw/azure-identity-qa  — same endpoint as the Logic App (search + detail)
- playbook-alert/common — public API for status lookup by ID
- playbook-alert/search — public API for finding fresh alerts when gateway is empty
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

    If the gateway returns 0 items (all previously-processed alerts are
    Dismissed/Resolved), fall back to the public RF API to find a fresh
    New alert and reset it via the gateway so it becomes visible again.
    """
    items = _gateway_search()
    if items:
        return items

    # Gateway empty — find a fresh New alert via the public API and reset it
    fresh_id = _find_fresh_alert_via_public_api()
    if fresh_id:
        reset_alert_to_new(fresh_id)
        import time; time.sleep(3)
        items = _gateway_search()

    return items


def _gateway_search() -> list[dict]:
    resp = _SESSION.post(
        f"{_GW_BASE}/playbook-alerts/search",
        json={"lookback_days": 21, "max_lookback_days": 21, "status": ["New"]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("pba_items", [])


def _find_fresh_alert_via_public_api() -> str | None:
    """
    Return the ID of a New identity_novel_exposures alert from the public
    RF API that is not already visible via the gateway. This is used as a
    seed when all gateway-visible alerts have been consumed by prior runs.
    """
    resp = _SESSION.post(
        f"{_PUBLIC_BASE}/search",
        json={
            "category": ["identity_novel_exposures"],
            "status": ["New"],
            "limit": 10,
        },
        timeout=30,
    )
    resp.raise_for_status()
    alerts = resp.json().get("data", [])
    return alerts[0]["playbook_alert_id"] if alerts else None


def reset_alert_to_new(alert_id: str) -> None:
    """Set the given alert back to New so the next scenario can consume it."""
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


def get_alert_status(alert_id: str) -> str:
    """Fetch current alert status via the public common endpoint."""
    resp = _SESSION.get(
        f"{_PUBLIC_BASE}/common/{alert_id}",
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    return data.get("status", "")
