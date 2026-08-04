"""
Recorded Future API client for Sentinel E2E tests.

Uses $AZURE_TOKEN_QA (standard RF API token, not Identity gateway).
Provides:
  - get_new_playbook_alert(): find a live "New" Playbook Alert to pin to
  - get_new_portal_alert(): find a live portal alert to pin to
"""
import requests

from . import config

_SESSION = requests.Session()
_SESSION.headers.update({
    "X-RFToken": config.RF_TOKEN,
    "Content-Type": "application/json",
})


def check_reachable() -> None:
    """
    Lightweight API ping — verifies the RF gateway is reachable and the token works.
    Called by the shared step_rf_api_reachable step.
    """
    resp = _SESSION.get(
        f"{config.RF_GW_BASE}/v2/alerts",
        params={"limit": 1},
        timeout=10,
    )
    resp.raise_for_status()
    print(f"\n  RF gateway reachable (status {resp.status_code})")


def get_new_playbook_alert() -> dict | None:
    """
    Return a "New" Playbook Alert using the same gateway endpoint and parameters
    as the recordedfuturev2 managed connector in the Logic App. This guarantees
    the selected alert will appear in the Logic App's search results.
    """
    resp = _SESSION.post(
        f"{config.RF_GW_BASE}/playbook-alert/search",
        json={"updated_from_relative": "-24", "categories": []},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json()
    if isinstance(items, list):
        return items[0] if items else None
    return items.get("data", [None])[0]


def get_new_portal_alert() -> dict | None:
    """
    Return a portal alert with at least 1 hit from the RF gateway API.
    The Alert-Importer writes one row per hit — an alert with 0 hits
    produces no LAW rows even if the run succeeds.
    """
    resp = _SESSION.get(
        f"{config.RF_GW_BASE}/v2/alerts",
        params={"limit": 50},
        timeout=30,
    )
    resp.raise_for_status()
    alerts = resp.json().get("data", [])
    # Prefer alerts with hits; fall back to first available
    with_hits = [a for a in alerts if a.get("hits")]
    return with_hits[0] if with_hits else (alerts[0] if alerts else None)
