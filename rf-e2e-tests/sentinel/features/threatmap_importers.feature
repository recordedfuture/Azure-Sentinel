@threatmap
Feature: RF Sentinel ThreatMap Importers → Log Analytics Workspace
  Tests RecordedFuture-ThreatMap-Importer and RecordedFuture-ThreatMapMalware-Importer.
  Each playbook sends the full current threat map as a single row per run
  (not one row per entity). Assert a new row appeared after the trigger.

  NOTE: workbooks RecordedFutureThreatActorHunting.json / RecordedFutureMalwareThreatHunting.json
  consume this data via mv-expand on the "data" column. Verifying the workbooks is a manual step.

  Background:
    Given az CLI is authenticated
    And resource group "rf-erik" exists
    And Log Analytics Workspace "ErikLogAnalyticWorkspace" is accessible
    And the RF API is reachable with token from "$AZURE_TOKEN_QA"
    And the shared RF connector "Recordedfuture-CustomConnector" is connected

  Scenario: threatmap - threat map imported to LAW
    Given API connections for logic app "threatmap" are authorized
    When I trigger logic app "threatmap" and wait for completion
    Then the logic app run status is "Succeeded"
    And within 10 minutes table "RecordedFutureThreatMap_V2_CL" has a row with JSON "data" array where each entry has keys "id, name, alias, categories, intent, opportunity, log_entries"

  Scenario: threatmap_malware - threat map malware imported to LAW
    Given API connections for logic app "threatmap_malware" are authorized
    When I trigger logic app "threatmap_malware" and wait for completion
    Then the logic app run status is "Succeeded"
    And within 10 minutes table "RecordedFutureThreatMapMalware_V2_CL" has a row with JSON "data" array where each entry has keys "id, name, alias, categories, prevalence, log_entries"
