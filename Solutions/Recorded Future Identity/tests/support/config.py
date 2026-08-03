"""
Central configuration for the RFI Alert Importer LAW integration tests.
All magic strings and env-var reads live here.
"""
import os
from datetime import date
from pathlib import Path

# ── Azure ────────────────────────────────────────────────────────────────────
SUBSCRIPTION_ID = "5129b3ff-c0c6-4e86-bd1c-70e5fcd579cf"
RESOURCE_GROUP = "rf-erik"
LAW_NAME = "ErikLogAnalyticWorkspace"
LAW_WORKSPACE_ID = "7479cf3e-cc64-43f7-b440-9a7afd21b2fc"
PORTAL_TENANT = "integrationsopsrecordedfutu.onmicrosoft.com"

# ── Entra ID ─────────────────────────────────────────────────────────────────
TEST_SECURITY_GROUP_ID = "006007f2-d235-4050-803d-599c32de9cc6"
TEST_USER_UPN = "test_compromised_user@integrationsopsrecordedfutu.onmicrosoft.com"
TEST_USER_OID = "2619357a-cdf4-401d-95df-ba756e4deed9"

# ── Recorded Future ──────────────────────────────────────────────────────────
RF_GW_BASE = "https://api.recordedfuture.com/gw/azure-identity-qa"
RF_TOKEN = os.environ["AZURE_IDENTITY_TOKEN_QA"]

# ── Logic App template ───────────────────────────────────────────────────────
TEMPLATE_PATH = (
    Path(__file__).parents[2]
    / "Playbooks"
    / "RFI-Playbook-Alert-Importer-LAW"
    / "azuredeploy.json"
)
RFI_CUSTOM_CONNECTOR = "RFI-CustomConnector-0-2-0"
LAW_TABLE = "RFI_PlaybookAlertResults_V2_CL"

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

# ARM parameters per scenario.
# NOTE: entra_user_upn is a test-only key — it is NOT an ARM parameter.
# environment.py pops it before calling az deployment group create, and passes
# it to patch_template() to inject the UPN override into the workflow definition.
# When entra_user_upn is None, the raw PBA identity flows through (user not found).
SCENARIO_PARAMS = {
    "nouser": {
        "entra_user_upn":                None,           # raw identity → 404 → Dismissed
        "PlaybookName":                  LOGIC_APP_NAMES["nouser"],
        "log_analytics_workspace_name":  LAW_NAME,
        "RFICustomConnector":            RFI_CUSTOM_CONNECTOR,
        "entra_id_domain":               "",
        "entra_id_security_group_id":    "",
        "confirm_user_as_risky":         False,
        "save_to_log_analytics_workspace": True,
        "create_role_assignment":        True,
    },
    "baseuser": {
        "entra_user_upn":                TEST_USER_UPN,  # hardcoded → 200 → Resolved
        "PlaybookName":                  LOGIC_APP_NAMES["baseuser"],
        "log_analytics_workspace_name":  LAW_NAME,
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
        "log_analytics_workspace_name":  LAW_NAME,
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
        "log_analytics_workspace_name":  LAW_NAME,
        "RFICustomConnector":            RFI_CUSTOM_CONNECTOR,
        "entra_id_domain":               "",
        "entra_id_security_group_id":    "",
        "confirm_user_as_risky":         False,
        "save_to_log_analytics_workspace": False,
        "create_role_assignment":        True,
    },
}

# Trigger timeout (seconds to wait for a run to leave "Running")
RUN_TIMEOUT_SECONDS = 180

LAW_POLL_TIMEOUT_SECONDS = 300
LAW_POLL_INTERVAL_SECONDS = 5

# ── v3.0 Identity API ─────────────────────────────────────────────────────────

V3_SEARCH_TEMPLATE_PATH = (
    Path(__file__).parents[2]
    / "Playbooks"
    / "v3.0"
    / "RFI-search-workforce-user"
    / "azuredeploy.json"
)
V3_LOOKUP_TEMPLATE_PATH = (
    Path(__file__).parents[2]
    / "Playbooks"
    / "v3.0"
    / "RFI-lookup-and-save-user"
    / "azuredeploy.json"
)

RFI_CUSTOM_CONNECTOR_V3 = "RFI-CustomConnector-0-1-0"

# Domain authorized for the QA RF token for credential search AND lookup.
V3_ORG_DOMAIN = "norsegods.online"

# Domain used for the UUID fake test email injected into fake search results.
# Must be authorized for the QA RF token so the lookup API accepts it.
V3_TEST_EMAIL_DOMAIN = "norsegods.online"

# Log Analytics tables written by the v3.0 playbooks
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

# ARM parameters per v3 scenario.
# NOTE: test_email is a test-only key populated at runtime in environment.py
# from context.v3_test_email. It is NOT an ARM parameter — environment.py
# pops it before calling az deployment group create and passes it to
# patch_search_template().
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

# Required API connections per v3 scenario key: {prefix: required}
# The v3 search playbooks create two connections:
#   - azuremonitorlogs-<name>: for the LAW dedup query — requires OAuth consent
#   - recordedfutureidenti-<name>: for the RF Identity API — api_key injected
#     programmatically in _setup_v3_rfi_connection(), no manual auth needed
V3_REQUIRED_CONN_PREFIXES = {
    "v3_workforce":         {"Azuremonitorlogs": True, "Recordedfutureidenti": True},
    "v3_workforce_nogroup": {"Azuremonitorlogs": True, "Recordedfutureidenti": True},
}

# PBA required connections (kept here alongside V3 for symmetry)
PBA_REQUIRED_CONN_PREFIXES = {
    "nouser":   {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": True},
    "baseuser": {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": True},
    "entra":    {"Azuread": True,  "Azureadip": True,  "Azuremonitorlogs": True},
    "nolaw":    {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": False},
}

# ── Merged lookups (used by step definitions) ─────────────────────────────────
# Single source of truth for any step that needs to look up a logic app name
# or its required connections by scenario key.
ALL_LOGIC_APP_NAMES: dict[str, str] = {**LOGIC_APP_NAMES, **V3_LOGIC_APP_NAMES}
ALL_REQUIRED_CONN_PREFIXES: dict[str, dict[str, bool]] = {
    **PBA_REQUIRED_CONN_PREFIXES,
    **V3_REQUIRED_CONN_PREFIXES,
}

