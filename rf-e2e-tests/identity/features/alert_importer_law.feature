@pba
Feature: RFI Alert Importer → Log Analytics Workspace
  Tests the RFI-Playbook-Alert-Importer-LAW logic app across four
  parameter configurations. Each scenario resets the pinned RF test
  alert to "New" before triggering, so they run sequentially against
  the same alert ID. All four logic app instances are deployed once
  (date-scoped names) and reused within the same day.

  Background:
    Given az CLI is authenticated
    And resource group "rf-erik" exists
    And Log Analytics Workspace "ErikLogAnalyticWorkspace" is accessible
    And the RF API is reachable with token from "$AZURE_IDENTITY_TOKEN_QA"
    And there is at least 1 New identity PBA available via the RF gateway
    And the test user "test_compromised_user@integrationsopsrecordedfutu.onmicrosoft.com" exists in Entra ID
    And the test security group "006007f2-d235-4050-803d-599c32de9cc6" exists in Entra ID
    And the test RF alert is reset to "New"

  Scenario: nouser - user not found, alert dismissed, LAW written, no Entra actions
    Given API connections for logic app "nouser" are authorized
    When I trigger logic app "nouser" and wait for completion
    Then the logic app run status is "Succeeded"
    And within 5 minutes table "RFI_PlaybookAlertResults_V2_CL" has at least 1 new row
    And the RF test alert status is "Dismissed"
    But the test user is not a member of security group "006007f2-d235-4050-803d-599c32de9cc6"
    And the test user is not marked as confirmed compromised in Entra ID

  Scenario: baseuser - user found via domain rewrite, alert resolved, LAW written, no Entra group/risky
    Given API connections for logic app "baseuser" are authorized
    When I trigger logic app "baseuser" and wait for completion
    Then the logic app run status is "Succeeded"
    And within 5 minutes table "RFI_PlaybookAlertResults_V2_CL" has at least 1 new row
    And the RF test alert status is "Resolved"
    But the test user is not a member of security group "006007f2-d235-4050-803d-599c32de9cc6"
    And the test user is not marked as confirmed compromised in Entra ID

  Scenario: entra - user found, added to security group and confirmed risky
    Given the test user is removed from security group "006007f2-d235-4050-803d-599c32de9cc6" if present
    And the test user risky state is dismissed in Entra ID if set
    And API connections for logic app "entra" are authorized
    When I trigger logic app "entra" and wait for completion
    Then the logic app run status is "Succeeded"
    And within 5 minutes table "RFI_PlaybookAlertResults_V2_CL" has at least 1 new row
    And the RF test alert status is "Resolved"
    And the test user is a member of security group "006007f2-d235-4050-803d-599c32de9cc6"
    And if Entra ID P1/P2 is available the test user is marked as confirmed compromised

  Scenario: nolaw - LAW write disabled, no data written, alert still resolved
    Given API connections for logic app "nolaw" are authorized
    When I trigger logic app "nolaw" and wait for completion
    Then the logic app run status is "Succeeded"
    And the RF test alert status is "Resolved"
    But table "RFI_PlaybookAlertResults_V2_CL" has no new rows within 1 minute
    And the test user is not a member of security group "006007f2-d235-4050-803d-599c32de9cc6"
