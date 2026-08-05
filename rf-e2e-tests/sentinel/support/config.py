"""
Sentinel-specific configuration.

Shared Azure constants imported from rf_e2e_tests.config_base.
Sentinel-specific constants (table names, app names, tokens, DCE/DCR) here.

TODO: audit for unused variables — some DCR/stream/table constants may no
longer be referenced directly now that the templates resolve them via
reference() at ARM deploy time.
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
    LAW_POLL_TIMEOUT_SECONDS,
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

# ── Sentinel DCE/DCR (deployed in rf-erik via azuredeploy-v2.json) ────────────
SENTINEL_DCE_ENDPOINT = "https://recorded-future-dce-8fgz.swedencentral-1.ingest.monitor.azure.com"

DCR_PLAYBOOK_ALERTS_IMMUTABLE_ID  = "dcr-fd9526788bf54504a3a5ebe7e3b09298"
DCR_CLASSIC_ALERTS_IMMUTABLE_ID   = "dcr-8e1ad77590874cc89dca3c4b3639c694"
DCR_THREATMAP_IMMUTABLE_ID        = "dcr-b645eba0f66841b1b2ba9cbf4213c4d9"
DCR_THREATMAP_MALWARE_IMMUTABLE_ID = "dcr-b1c1396af35d4219a843d6f49790cccd"

STREAM_PLAYBOOK_ALERTS  = "Custom-RecordedFuturePlaybookAlerts_V2_CL"
STREAM_CLASSIC_ALERTS   = "Custom-RecordedFutureClassicAlerts_V2_CL"
STREAM_THREATMAP        = "Custom-RecordedFutureThreatMap_V2_CL"
STREAM_THREATMAP_MALWARE = "Custom-RecordedFutureThreatMapMalware_V2_CL"

# ── Log Analytics tables ──────────────────────────────────────────────────────
TABLE_PLAYBOOK_ALERTS   = "RecordedFuturePlaybookAlerts_V2_CL"
TABLE_CLASSIC_ALERTS    = "RecordedFutureClassicAlerts_V2_CL"
TABLE_THREATMAP         = "RecordedFutureThreatMap_V2_CL"
TABLE_THREATMAP_MALWARE = "RecordedFutureThreatMapMalware_V2_CL"

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


# ── Test Logic App names (date-scoped + suffix) ───────────────────────────────
_TODAY = date.today().strftime("%Y%m%d")
# Bump _SUFFIX to force fresh apps (new MSIs, clean role assignments).
_SUFFIX = "v9"

LOGIC_APP_NAMES = {
    "playbook_alert_importer": f"rf-sent-{_TODAY}-{_SUFFIX}-pba",
    "alert_importer":          f"rf-sent-{_TODAY}-{_SUFFIX}-alert",
    "threatmap":               f"rf-sent-{_TODAY}-{_SUFFIX}-threatmap",
    "threatmap_malware":       f"rf-sent-{_TODAY}-{_SUFFIX}-threatmap-mal",
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
}

# Required API connections per scenario: {prefix: required}
# RecordedFuture-ConnectorV2 is shared and already Connected — checked globally.
# alert_importer also needs azuremonitorlogs for the watermark query.
REQUIRED_CONN_PREFIXES = {
    "playbook_alert_importer": {"Azuremonitorlogs": False},
    "alert_importer":          {"Azuremonitorlogs": True},
    "threatmap":               {},
    "threatmap_malware":       {},
}

ALL_LOGIC_APP_NAMES = LOGIC_APP_NAMES
ALL_REQUIRED_CONN_PREFIXES = REQUIRED_CONN_PREFIXES
