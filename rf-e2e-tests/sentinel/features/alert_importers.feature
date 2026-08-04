@alerts
Feature: RF Sentinel Alert Importers → Log Analytics Workspace
  Tests RecordedFuture-Playbook-Alert-Importer and RecordedFuture-Alert-Importer.
  Each run dynamically pins to a live RF alert so assertions are specific, not
  just "some row appeared". Both Logic Apps are deployed once (date-scoped names)
  and reused within the same day.

  Background:
    Given az CLI is authenticated
    And resource group "rf-erik" exists
    And Log Analytics Workspace "ErikLogAnalyticWorkspace" is accessible
    And the RF API is reachable with token from "$AZURE_TOKEN_QA"
    And the shared RF connector "RecordedFuture-ConnectorV2" is connected

  Scenario: playbook_alert_importer - playbook alert imported to LAW
    Given API connections for logic app "playbook_alert_importer" are authorized
    When I trigger logic app "playbook_alert_importer" and wait for completion
    Then the logic app run status is "Succeeded"
    And within 5 minutes table "RecordedFuturePlaybookAlerts_V2_CL" has a row where "id" equals the pinned playbook alert id

  Scenario: alert_importer - portal alert imported to LAW
    Given API connections for logic app "alert_importer" are authorized
    When I trigger logic app "alert_importer" and wait for completion
    Then the logic app run status is "Succeeded"
    And within 5 minutes table "RecordedFutureClassicAlerts_V2_CL" has at least 1 new row
