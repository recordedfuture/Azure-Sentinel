@threatmap
Feature: RF Sentinel ThreatMap Importers → Log Analytics Workspace
  Tests RecordedFuture-ThreatMap-Importer and RecordedFuture-ThreatMapMalware-Importer.
  Each playbook sends the full current threat map as a single row per run
  (not one row per entity) — no alert pinning, just assert a new row appeared
  after the trigger. The row's "data" column is a JSON-encoded array string of
  entity objects; assertions parse it and check its shape (non-empty array,
  expected keys per entity) rather than just checking row count.

  NOTE: RecordedFutureThreatActorHunting.json / RecordedFutureMalwareThreatHunting.json
  consume this data via mv-expand on the "data" column. Verifying the workbook JSON
  parses/queries correctly against real ingested data is a manual/portal step —
  the visual rendering (charts, filters) can't reasonably be asserted in an
  automated Behave test. Do not try to automate that here.

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
