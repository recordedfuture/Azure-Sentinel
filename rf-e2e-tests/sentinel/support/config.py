"""
Sentinel-specific configuration.

Shared Azure constants imported from rf_e2e_tests.config_base.
Sentinel-specific constants (table names, app names, tokens, DCE/DCR) here.
"""
import os
import uuid
from datetime import date
from pathlib import Path

# ── Shared Azure constants ────────────────────────────────────────────────────
from rf_e2e_tests.config_base import (  # noqa: F401
    SUBSCRIPTION_ID,
    RESOURCE_GROUP,
    LAW_NAME,
    LAW_WORKSPACE_ID,
    PORTAL_TENANT,
    RUN_TIMEOUT_SECONDS,
    LAW_POLL_INTERVAL_SECONDS,
)

# MSI-authenticated connections (azuremonitorlogs with managedIdentityAuth)
# report "Ready" instead of "Connected" — both are valid in this suite.
VALID_CONN_STATUSES = {"Connected", "Ready"}

# ── Recorded Future ───────────────────────────────────────────────────────────
RF_TOKEN = os.environ["AZURE_TOKEN_QA"]
RF_API_BASE = "https://api.recordedfuture.com"
RF_GW_BASE = "https://api.recordedfuture.com/gw/azure-qa"

# ── Logic App template paths ──────────────────────────────────────────────────
_SOLUTIONS = Path(__file__).parents[3] / "Solutions" / "Recorded Future"

TEMPLATE_PLAYBOOK_ALERT_IMPORTER = (
    _SOLUTIONS / "Playbooks" / "Alerts"
    / "RecordedFuture-Playbook-Alert-Importer" / "azuredeploy.json"
)
TEMPLATE_ALERT_IMPORTER = (
    _SOLUTIONS / "Playbooks" / "Alerts"
    / "RecordedFuture-Alert-Importer" / "azuredeploy.json"
)
TEMPLATE_THREATMAP_IMPORTER = (
    _SOLUTIONS / "Playbooks" / "ThreatHunting"
    / "RecordedFuture-ThreatMap-Importer" / "azuredeploy.json"
)
TEMPLATE_THREATMAP_MALWARE_IMPORTER = (
    _SOLUTIONS / "Playbooks" / "ThreatHunting"
    / "RecordedFuture-ThreatMapMalware-Importer" / "azuredeploy.json"
)
TEMPLATE_SANDBOX_STORAGE_ACCOUNT = (
    _SOLUTIONS / "Playbooks" / "Sandboxing"
    / "RecordedFuture-Sandbox_StorageAccount" / "azuredeploy.json"
)

# ── ThreatHunting workbooks (deployed alongside the ThreatMap playbooks) ──────
# Like the analytic rules, these are deployed idempotently with a fixed,
# deterministic resource name/ID on every before_all — no date/suffix scoping
# — so re-running the suite always updates the same workbook resource in
# place rather than creating a new one each day.
_WORKBOOKS_DIR = _SOLUTIONS / "Workbooks"

WORKBOOK_TEMPLATES = {
    "threatactor_workbook": {
        "path": _WORKBOOKS_DIR / "RecordedFutureThreatActorHunting.json",
        "display_name": "Recorded Future - Threat Actor Hunting",
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "rf-e2e-threatactor-workbook")),
    },
    "malware_workbook": {
        "path": _WORKBOOKS_DIR / "RecordedFutureMalwareThreatHunting.json",
        "display_name": "Recorded Future - Malware Threat Hunting",
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "rf-e2e-malware-workbook")),
    },
}


# ── Shared RF connection (already Connected in rf-erik) ───────────────────────
RF_CONNECTION_NAME = "RecordedFuture-ConnectorV2"

# ── Shared RF custom connector used by the ThreatMap playbooks ────────────────
# (a different Microsoft.Web/connections resource than RF_CONNECTION_NAME above
# — backed by Microsoft.Web/customApis/RecordedFuture-CustomConnector, whose
# swagger bakes in host=api.recordedfuture.com, basePath=/gw/azure and exposes
# a single connectionParameter: api_key (securestring). Its value isn't
# readable via GET (Azure never returns secure connection params), so the
# fix-if-needed step always (re)sets it rather than trying to detect staleness.
RF_CUSTOM_CONNECTOR_NAME = "Recordedfuture-CustomConnector"

# ── Sandbox playbooks ──────────────────────────────────────────────────────────
# RecordedFuture-Sandbox_StorageAccount's blob-fetch actions have a HARDCODED
# blob path baked into the ARM template itself (base64-encoded action metadata,
# not a parameter): container "testing", blob "calc.exe". These names are not
# configurable — the fixture must create a storage account with exactly this
# container/blob, matching the template, not the other way around.
SANDBOX_STORAGE_ACCOUNT_NAME = "rfe2esandboxsa"
SANDBOX_BLOB_CONTAINER = "testing"
SANDBOX_BLOB_NAME = "calc.exe"
SANDBOX_BLOB_CONTENT = (
    b"This is a placeholder test file used for Recorded Future Sandbox E2E "
    b"testing. It is plain text, not a real executable, despite the .exe name "
    b"(required to match a hardcoded path in the ARM template)."
)

# Sandbox API credentials — TWO separate things are needed, both using the
# same $SANDBOX_API_PROD token (confirmed live; the AZURE_SANDBOX_TOKEN_*
# variants all gave 401 "Bad authorization token" at the actual scan step):
#   1. Recordedfuturesandbo connection-level api_key (a real connectionParameter
#      on this connector, unlike RF_CUSTOM_CONNECTOR_NAME's ThreatMap swagger-
#      only connector) — fixed via ensure_sandbox_connector_configured().
#   2. The "Enterprise Sandbox API Key" ARM parameter, passed per-action as a
#      SandboxToken header by the playbook itself (not connection-level).
SANDBOX_API_TOKEN = os.environ["SANDBOX_API_PROD"]
SANDBOX_CONNECTOR_NAME = "Recordedfuture-SandboConnection"


# ── Test Logic App names (date-scoped + suffix) ───────────────────────────────
_TODAY = date.today().strftime("%Y%m%d")
# Bump _SUFFIX to force fresh apps (new MSIs, clean role assignments).
_SUFFIX = "v9"

LOGIC_APP_NAMES = {
    "playbook_alert_importer": f"rf-sent-{_TODAY}-{_SUFFIX}-pba",
    "alert_importer":          f"rf-sent-{_TODAY}-{_SUFFIX}-alert",
    "threatmap":               f"rf-sent-{_TODAY}-{_SUFFIX}-threatmap",
    "threatmap_malware":       f"rf-sent-{_TODAY}-{_SUFFIX}-threatmap-mal",
    "sandbox_storage_account": f"rf-sent-{_TODAY}-{_SUFFIX}-sandbox-sa",
}

# ARM parameters per scenario (DceEndpoint/DcrImmutableId/StreamName passed explicitly
# since Sentinel templates take them as ARM params, not via reference())
SCENARIO_PARAMS = {
    "playbook_alert_importer": {
        "PlaybookName":           LOGIC_APP_NAMES["playbook_alert_importer"],
        "create_role_assignment": True,
    },
    "alert_importer": {
        "PlaybookName":    LOGIC_APP_NAMES["alert_importer"],
        "workspace_name":  LAW_NAME,
        "create_role_assignment": True,
    },
    "threatmap": {
        "PlaybookName": LOGIC_APP_NAMES["threatmap"],
        "create_role_assignment": True,
    },
    "threatmap_malware": {
        "PlaybookName": LOGIC_APP_NAMES["threatmap_malware"],
        "create_role_assignment": True,
    },
    "sandbox_storage_account": {
        "PlaybookName": LOGIC_APP_NAMES["sandbox_storage_account"],
        "Enterprise Sandbox API Key": SANDBOX_API_TOKEN,
        "create_role_assignment": True,
    },
}

# Required API connections per scenario: {prefix: required}
# RecordedFuture-ConnectorV2 is shared and already Connected — checked globally.
# alert_importer also needs azuremonitorlogs for the watermark query.
# sandbox_storage_account's Azureblob-* connection is fixed up directly by
# ensure_blob_storage_configured() in before_all (real accountName/accessKey),
# not via the OAuth-consent flow, so it's not listed here as "required".
REQUIRED_CONN_PREFIXES = {
    "playbook_alert_importer": {"Azuremonitorlogs": False},
    "alert_importer":          {"Azuremonitorlogs": True},
    "threatmap":               {},
    "threatmap_malware":       {},
    "sandbox_storage_account": {},
}

ALL_LOGIC_APP_NAMES = LOGIC_APP_NAMES
ALL_REQUIRED_CONN_PREFIXES = REQUIRED_CONN_PREFIXES

# Per-scenario override of RUN_TIMEOUT_SECONDS, read by the shared
# step_trigger_and_wait step. Only sandbox_storage_account needs longer than
# the default 180s — it makes a real external API call (submit file to RF
# Sandbox, poll for a report) that took ~3-6 minutes in live testing. Every
# other scenario keeps the default, unaffected.
RUN_TIMEOUT_OVERRIDES = {
    "sandbox_storage_account": 600,
}
