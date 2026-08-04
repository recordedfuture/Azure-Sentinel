"""
Shared constants for RF E2E test suites.

Suite-specific config (tokens, app names, table names) lives in
identity/support/config.py and sentinel/support/config.py respectively.
Both import from here for the shared Azure environment values.
"""

SUBSCRIPTION_ID = "5129b3ff-c0c6-4e86-bd1c-70e5fcd579cf"
RESOURCE_GROUP = "rf-erik"
LAW_NAME = "ErikLogAnalyticWorkspace"
LAW_WORKSPACE_ID = "7479cf3e-cc64-43f7-b440-9a7afd21b2fc"
PORTAL_TENANT = "integrationsopsrecordedfutu.onmicrosoft.com"

# Connection statuses considered "authorized" for step assertions.
# Suites using MSI-authenticated connectors (which report "Ready") should
# override this in their support/config.py.
VALID_CONN_STATUSES = {"Connected"}

# Shared timeouts (suites may override in their own config)
RUN_TIMEOUT_SECONDS = 180
LAW_POLL_TIMEOUT_SECONDS = 300
LAW_POLL_INTERVAL_SECONDS = 5
