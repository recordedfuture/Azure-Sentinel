"""
Sandbox-specific Azure client helpers.

Fixtures and connection fixes for RecordedFuture-Sandbox_StorageAccount,
split out from az_client.py to keep that file focused on generic
Sentinel-wide helpers.
"""
# support/__init__.py adds rf-e2e-tests root to sys.path
from rf_e2e_tests.az_client import _rest, _run

from . import config


# ── Sandbox StorageAccount fixture ────────────────────────────────────────────
#
# RecordedFuture-Sandbox_StorageAccount's blob-fetch actions have a hardcoded
# blob path baked into the ARM template (container "testing", blob "calc.exe"
# — see config.SANDBOX_BLOB_CONTAINER/SANDBOX_BLOB_NAME). This fixture creates
# a dedicated, suite-owned storage account/container/blob matching that path
# (idempotent — safe to call on every before_all) and is intentionally NOT
# torn down between runs (storage accounts/blobs are cheap and stable; tearing
# down and recreating one on every run would only add latency/fragility).

def ensure_sandbox_storage_fixture(
    account_name: str = config.SANDBOX_STORAGE_ACCOUNT_NAME,
    rg: str = config.RESOURCE_GROUP,
    container: str = config.SANDBOX_BLOB_CONTAINER,
    blob_name: str = config.SANDBOX_BLOB_NAME,
    blob_content: bytes = config.SANDBOX_BLOB_CONTENT,
) -> str:
    """
    Ensure the sandbox test storage account/container/blob exist. Returns the
    storage account's primary key (needed to wire the Azureblob-* connection).
    """
    existing = _run(
        "storage", "account", "show",
        "--name", account_name, "--resource-group", rg, check=False,
    )
    if not existing:
        print(f"\n  Creating storage account '{account_name}'...")
        _run(
            "storage", "account", "create",
            "--name", account_name, "--resource-group", rg,
            "--sku", "Standard_LRS", "--kind", "StorageV2", check=False,
        )
    else:
        print(f"\n  Storage account '{account_name}' already exists")

    keys = _run(
        "storage", "account", "keys", "list",
        "--account-name", account_name, "--resource-group", rg,
    )
    account_key = keys[0]["value"]

    existing_container = _run(
        "storage", "container", "show",
        "--name", container, "--account-name", account_name,
        "--account-key", account_key, check=False,
    )
    if not existing_container:
        print(f"  Creating container '{container}'...")
        _run(
            "storage", "container", "create",
            "--name", container, "--account-name", account_name,
            "--account-key", account_key, check=False,
        )

    existing_blob = _run(
        "storage", "blob", "show",
        "--container-name", container, "--name", blob_name,
        "--account-name", account_name, "--account-key", account_key, check=False,
    )
    if not existing_blob:
        print(f"  Uploading blob '{container}/{blob_name}'...")
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(blob_content)
            tmp_path = f.name
        try:
            _run(
                "storage", "blob", "upload",
                "--container-name", container, "--name", blob_name,
                "--file", tmp_path, "--account-name", account_name,
                "--account-key", account_key, "--overwrite", "true", check=False,
            )
        finally:
            import os as _os
            _os.unlink(tmp_path)
    else:
        print(f"  Blob '{container}/{blob_name}' already exists")

    print(f"  Sandbox storage fixture ready: {account_name}/{container}/{blob_name}")
    return account_key


def ensure_sandbox_connector_configured(
    conn_name: str = config.SANDBOX_CONNECTOR_NAME,
    rg: str = config.RESOURCE_GROUP,
) -> None:
    """
    Fix the shared Recordedfuturesandbo connection's api_key. Unlike the
    ThreatMap custom connector (swagger-only, no real connectionParameters),
    this one is a genuine managed API with a required `api_key`
    connectionParameter — confirmed live: without it, Submit_file_samples
    401s with "Bad authorization token" even though the per-action
    SandboxToken header (config.SANDBOX_API_TOKEN, passed via the
    "Enterprise Sandbox API Key" ARM parameter) is also correct. Both use the
    same $SANDBOX_API_PROD token. Idempotent — safe to call on every before_all.
    """
    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Web/connections/{conn_name}?api-version=2016-06-01"
    )
    body = _rest("GET", url, check=False)
    assert body, f"Sandbox connection '{conn_name}' not found in {rg}"

    props = body.get("properties", {})
    props["customParameterValues"] = {"api_key": config.SANDBOX_API_TOKEN}
    body["properties"] = props
    for key in ("id", "name", "type"):
        body.pop(key, None)
    _rest("PUT", url, body)
    print(f"  Sandbox connection '{conn_name}' api_key (re)set")


def ensure_blob_connection_configured(
    playbook_name: str,
    account_name: str = config.SANDBOX_STORAGE_ACCOUNT_NAME,
    account_key: str = None,
    rg: str = config.RESOURCE_GROUP,
) -> None:
    """
    Wire real storage credentials into the fresh-per-day
    `Azureblob-{playbook_name}` connection (deployed by the ARM template
    unauthorized). Idempotent PUT.

    Unlike the RF custom connector (a single flat `customParameterValues`),
    Azure Blob Storage's managed connector exposes multiple auth modes via
    `connectionParameterSets` (service-principal, key-based, managed-identity,
    ...), so it requires the `parameterValueSet` structure — {name, values} —
    naming which set to use ("keyBasedAuth": accountName/accessKey), not a
    flat customParameterValues dict. Confirmed via the azureblob managedApis
    definition's connectionParameterSets and by testing both shapes live —
    customParameterValues silently no-ops (PUT succeeds, status stays
    ConfigurationNeeded) for connectors with parameter *sets*.
    """
    if account_key is None:
        keys = _run(
            "storage", "account", "keys", "list",
            "--account-name", account_name, "--resource-group", rg,
        )
        account_key = keys[0]["value"]

    conn_name = f"Azureblob-{playbook_name}"
    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Web/connections/{conn_name}?api-version=2016-06-01"
    )
    body = _rest("GET", url, check=False)
    assert body, f"Azureblob connection '{conn_name}' not found in {rg}"

    props = body.get("properties", {})
    props["parameterValueSet"] = {
        "name": "keyBasedAuth",
        "values": {
            "accountName": {"value": account_name},
            "accessKey": {"value": account_key},
        },
    }
    body["properties"] = props
    for key in ("id", "name", "type"):
        body.pop(key, None)
    _rest("PUT", url, body)
    print(f"  Azureblob connection '{conn_name}' wired to storage account '{account_name}'")
