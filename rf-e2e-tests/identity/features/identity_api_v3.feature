@v3
Feature: RFI Identity API v3.0 → Log Analytics Workspace
  Tests the v3.0 Identity API playbooks (RFI-search-workforce-user +
  RFI-lookup-and-save-user) across two parameter configurations.

  The real RF credential/malware search API is called in both scenarios, but
  its results are replaced with a single fake UUID email
  (test-<uuid>@norsegods.online) generated fresh per scenario per suite run.
  This ensures the LAW dedup query always returns empty (UUID was never seen
  before) without needing to clear the tables between runs. A separate UUID
  is generated per scenario to prevent cross-scenario dedup collisions.
  All three v3.0 Logic App instances (lookup + 2 search variants) are deployed
  once (date-scoped names) and reused within the same day.

  Background:
    Given az CLI is authenticated
    And resource group "rf-erik" exists
    And Log Analytics Workspace "ErikLogAnalyticWorkspace" is accessible
    And the RF API is reachable with token from "$AZURE_IDENTITY_TOKEN_QA"
    And the test user "test_compromised_user@integrationsopsrecordedfutu.onmicrosoft.com" exists in Entra ID
    And the test security group "006007f2-d235-4050-803d-599c32de9cc6" exists in Entra ID

  Scenario: v3_workforce - exposures found, all three LAW tables written, user added to security group
    Given the test user is removed from security group "006007f2-d235-4050-803d-599c32de9cc6" if present
    And API connections for logic app "v3_workforce" are authorized
    When I trigger logic app "v3_workforce" and wait for completion
    Then within 5 minutes table "RFI_CredentialDumps_V2_CL" has at least 1 new row
    And within 5 minutes table "RFI_MalwareLogs_V2_CL" has at least 1 new row
    And within 5 minutes table "RFI_UsersLookupResults_V2_CL" has at least 1 new row
    And the test user is a member of security group "006007f2-d235-4050-803d-599c32de9cc6"

  Scenario: v3_workforce_nogroup - exposures found, all three LAW tables written, no group action
    Given API connections for logic app "v3_workforce_nogroup" are authorized
    When I trigger logic app "v3_workforce_nogroup" and wait for completion
    Then within 5 minutes table "RFI_CredentialDumps_V2_CL" has at least 1 new row
    And within 5 minutes table "RFI_MalwareLogs_V2_CL" has at least 1 new row
    And within 5 minutes table "RFI_UsersLookupResults_V2_CL" has at least 1 new row
    But the test user is not a member of security group "006007f2-d235-4050-803d-599c32de9cc6"

    # TODO: are there more things to test?