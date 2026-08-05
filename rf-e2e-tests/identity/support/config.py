"""
Identity-specific configuration.

Shared Azure constants (SUBSCRIPTION_ID, RESOURCE_GROUP, etc.) are imported
from rf_e2e_tests.config_base. Identity-specific constants are defined here.

TODO: audit for unused variables — some constants (e.g. IDENTITY_DCE_ENDPOINT,
IDENTITY_DCR_* IDs) were added as reference values but may not be read by any
test code now that the templates resolve them via reference() at ARM deploy time.
"""
import os
from datetime import date
from pathlib import Path

# ── Shared Azure constants ────────────────────────────────────────────────────
# support/__init__.py adds rf-e2e-tests root to sys.path
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

# ── Entra ID ─────────────────────────────────────────────────────────────────
TEST_SECURITY_GROUP_ID = "006007f2-d235-4050-803d-599c32de9cc6"
TEST_USER_UPN = "test_compromised_user@integrationsopsrecordedfutu.onmicrosoft.com"
TEST_USER_OID = "2619357a-cdf4-401d-95df-ba756e4deed9"

# ── Recorded Future ──────────────────────────────────────────────────────────
RF_GW_BASE = "https://api.recordedfuture.com/gw/azure-identity-qa"
RF_TOKEN = os.environ["AZURE_IDENTITY_TOKEN_QA"]

# ── Logic App template paths ─────────────────────────────────────────────────
# Paths are relative to the Solutions/ directory, two levels up from identity/support/
_SOLUTIONS = Path(__file__).parents[3] / "Solutions"

TEMPLATE_PATH = (
    _SOLUTIONS
    / "Recorded Future Identity"
    / "Playbooks"
    / "RFI-Playbook-Alert-Importer-LAW"
    / "azuredeploy.json"
)
RFI_CUSTOM_CONNECTOR = "RFI-CustomConnector-0-2-0"
LAW_TABLE = "RFI_PlaybookAlertResults_V2_CL"

# ── Identity Alert Importer DCE/DCR (deployed in rf-erik) ────────────────────
IDENTITY_DCE_ENDPOINT = "https://recorded-future-identity-dce-o842.swedencentral-1.ingest.monitor.azure.com"
IDENTITY_DCR_PLAYBOOK_ALERTS_IMMUTABLE_ID = "dcr-79e03c11db09440c952541675276da3b"
IDENTITY_STREAM_PLAYBOOK_ALERTS = "Custom-RFI_PlaybookAlertResults_V2_CL"

# ── Test logic app names ──────────────────────────────────────────────────────
_TODAY = date.today().strftime("%Y%m%d")
# Bump _SUFFIX when you need completely fresh apps (new MSIs, clean role assignments).
_SUFFIX = "v3"

LOGIC_APP_NAMES = {
    "nouser":   f"rfi-al-law-{_TODAY}-{_SUFFIX}-nouser",
    "baseuser": f"rfi-al-law-{_TODAY}-{_SUFFIX}-baseuser",
    "entra":    f"rfi-al-law-{_TODAY}-{_SUFFIX}-entra",
    "nolaw":    f"rfi-al-law-{_TODAY}-{_SUFFIX}-nolaw",
}

SCENARIO_PARAMS = {
    "nouser": {
        "entra_user_upn":                None,
        "PlaybookName":                  LOGIC_APP_NAMES["nouser"],
        "RFICustomConnector":            RFI_CUSTOM_CONNECTOR,
        "entra_id_domain":               "",
        "entra_id_security_group_id":    "",
        "confirm_user_as_risky":         False,
        "save_to_log_analytics_workspace": True,
        "create_role_assignment":        True,
    },
    "baseuser": {
        "entra_user_upn":                TEST_USER_UPN,
        "PlaybookName":                  LOGIC_APP_NAMES["baseuser"],
        "RFICustomConnector":            RFI_CUSTOM_CONNECTOR,
        "entra_id_domain":               "",
        "entra_id_security_group_id":    "",
        "confirm_user_as_risky":         False,
        "save_to_log_analytics_workspace": True,
        "create_role_assignment":        True,
    },
    "entra": {
        "entra_user_upn":                TEST_USER_UPN,
        "PlaybookName":                  LOGIC_APP_NAMES["entra"],
        "RFICustomConnector":            RFI_CUSTOM_CONNECTOR,
        "entra_id_domain":               "",
        "entra_id_security_group_id":    TEST_SECURITY_GROUP_ID,
        "confirm_user_as_risky":         True,
        "save_to_log_analytics_workspace": True,
        "create_role_assignment":        True,
    },
    "nolaw": {
        "entra_user_upn":                TEST_USER_UPN,
        "PlaybookName":                  LOGIC_APP_NAMES["nolaw"],
        "RFICustomConnector":            RFI_CUSTOM_CONNECTOR,
        "entra_id_domain":               "",
        "entra_id_security_group_id":    "",
        "confirm_user_as_risky":         False,
        "save_to_log_analytics_workspace": False,
        "create_role_assignment":        True,
    },
}

# ── v3.0 Identity API ─────────────────────────────────────────────────────────

V3_SEARCH_TEMPLATE_PATH = (
    _SOLUTIONS
    / "Recorded Future Identity"
    / "Playbooks"
    / "v3.0"
    / "RFI-search-workforce-user"
    / "azuredeploy.json"
)
V3_LOOKUP_TEMPLATE_PATH = (
    _SOLUTIONS
    / "Recorded Future Identity"
    / "Playbooks"
    / "v3.0"
    / "RFI-lookup-and-save-user"
    / "azuredeploy.json"
)

RFI_CUSTOM_CONNECTOR_V3 = "RFI-CustomConnector-0-1-0"
V3_ORG_DOMAIN = "norsegods.online"
V3_TEST_EMAIL_DOMAIN = "norsegods.online"

V3_LAW_TABLES = [
    "RFI_CredentialDumps_V2_CL",
    "RFI_MalwareLogs_V2_CL",
    "RFI_UsersLookupResults_V2_CL",
]

V3_LOGIC_APP_NAMES = {
    "v3_workforce":         f"rfi-id-v3-{_TODAY}-{_SUFFIX}-workforce",
    "v3_workforce_nogroup": f"rfi-id-v3-{_TODAY}-{_SUFFIX}-nogroup",
    "v3_lookup":            f"rfi-id-v3-{_TODAY}-{_SUFFIX}-lookup",
}

V3_SCENARIO_PARAMS = {
    "v3_workforce": {
        "PlaybookName":                              V3_LOGIC_APP_NAMES["v3_workforce"],
        "workspace_name":                            LAW_NAME,
        "Playbook-Name-lookup-and-save-user":        V3_LOGIC_APP_NAMES["v3_lookup"],
        "Playbook-Name-add-EntraID-security-group-user": "RFI-add-EntraID-security-group-user",
        "Playbook-Name-confirm-EntraID-risky-user":  "RFI-confirm-EntraID-risky-user",
        "create_role_assignment":                    True,
    },
    "v3_workforce_nogroup": {
        "PlaybookName":                              V3_LOGIC_APP_NAMES["v3_workforce_nogroup"],
        "workspace_name":                            LAW_NAME,
        "Playbook-Name-lookup-and-save-user":        V3_LOGIC_APP_NAMES["v3_lookup"],
        "Playbook-Name-add-EntraID-security-group-user": "RFI-add-EntraID-security-group-user",
        "Playbook-Name-confirm-EntraID-risky-user":  "RFI-confirm-EntraID-risky-user",
        "create_role_assignment":                    True,
    },
}

V3_REQUIRED_CONN_PREFIXES = {
    "v3_workforce":         {"Azuremonitorlogs": True, "Recordedfutureidenti": True},
    "v3_workforce_nogroup": {"Azuremonitorlogs": True, "Recordedfutureidenti": True},
}

PBA_REQUIRED_CONN_PREFIXES = {
    "nouser":   {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": True},
    "baseuser": {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": True},
    "entra":    {"Azuread": True,  "Azureadip": True,  "Azuremonitorlogs": True},
    "nolaw":    {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": False},
}

ALL_LOGIC_APP_NAMES: dict[str, str] = {**LOGIC_APP_NAMES, **V3_LOGIC_APP_NAMES}
ALL_REQUIRED_CONN_PREFIXES: dict[str, dict[str, bool]] = {
    **PBA_REQUIRED_CONN_PREFIXES,
    **V3_REQUIRED_CONN_PREFIXES,
}
