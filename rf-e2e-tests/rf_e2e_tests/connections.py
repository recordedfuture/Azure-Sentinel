"""
Shared connection authorization helpers.

Used by both identity and sentinel environment.py to check connections
and open OAuth consent URLs when required.
"""
import subprocess

from rf_e2e_tests import az_client as _az


def _consent_url(conn_name: str, subscription_id: str, resource_group: str) -> str | None:
    result = _az._rest(
        "POST",
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Web/connections/{conn_name}"
        f"/listConsentLinks?api-version=2016-06-01",
        {"parameters": [{"parameterName": "token", "redirectUrl": "https://portal.azure.com/"}]},
        check=False,
    )
    if not result:
        return None
    links = result.get("value", [])
    return links[0].get("link") if links else None


def _check(app_names: dict, required_prefixes: dict, valid_statuses: set) -> dict:
    """Return {key: [(conn_name, status)]} for every required connection not in valid_statuses."""
    from rf_e2e_tests.az_client import get_connection_status
    unconnected = {}
    for key, la_name in app_names.items():
        bad = []
        for prefix, required in required_prefixes.get(key, {}).items():
            conn = f"{prefix}-{la_name}"
            status = get_connection_status(conn)
            if required and status not in valid_statuses:
                bad.append((conn, status or "not found"))
        if bad:
            unconnected[key] = bad
    return unconnected


def authorize_if_needed(
    app_names: dict,
    required_prefixes: dict,
    subscription_id: str,
    resource_group: str,
    valid_statuses: set | None = None,
) -> None:
    """
    Check all required connections. If any are not in valid_statuses, open
    consent URLs in the browser and prompt the user once to continue.
    """
    if valid_statuses is None:
        valid_statuses = {"Connected"}

    unconnected = _check(app_names, required_prefixes, valid_statuses)
    if not unconnected:
        print("  All required connections are Connected.")
        return

    all_urls = []
    for key, bad_conns in unconnected.items():
        for conn_name, _ in bad_conns:
            url = _consent_url(conn_name, subscription_id, resource_group)
            if url:
                all_urls.append((conn_name, url))

    if not all_urls:
        return

    print(f"\n  {len(all_urls)} connection(s) need authorization — opening in browser...")
    for conn_name, url in all_urls:
        print(f"    {conn_name}")
        subprocess.run(["open", url], check=False)

    print("\n  Authorize each connection tab, then press Enter to continue...")
    try:
        with open("/dev/tty") as tty:
            tty.readline()
    except OSError:
        raise RuntimeError(
            "Cannot read from terminal. Run behave in an interactive terminal session."
        )

    still_bad = _check(app_names, required_prefixes, valid_statuses)
    assert not still_bad, (
        "Some connections still not authorized after confirmation:\n"
        + "\n".join(
            f"  {key}: {[c for c, _ in conns]}"
            for key, conns in still_bad.items()
        )
    )
    print("  All connections now Connected.")
