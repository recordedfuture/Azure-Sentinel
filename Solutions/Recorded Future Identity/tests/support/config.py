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
