@sandbox
Feature: RF Sentinel Sandbox Importers → Log Analytics Workspace
  Tests RecordedFuture-Sandbox_StorageAccount: submits a fixed test blob
  (container "testing", blob "calc.exe" — hardcoded in the ARM template) to
  the RF Sandbox and asserts the result lands in
  RecordedFutureSandboxResults_V2_CL. Storage fixture is idempotent and
  persists between runs (sandbox_client.ensure_sandbox_storage_fixture()).

  SandboxVerdict/SampleId can legitimately be empty for benign scans, so only
  FileName/SandboxScore/HtmlReport/ScanTime are asserted non-empty.

  NOT covered: RecordedFuture-Sandbox_Outlook_Attachment (needs a real
  OAuth-authorized Outlook mailbox) and incident-creation (no safe
  way to make a benign scan score high enough to trigger the analytic rules).

  Background:
    Given az CLI is authenticated
    And resource group "rf-erik" exists
    And Log Analytics Workspace "ErikLogAnalyticWorkspace" is accessible

  Scenario: sandbox_storage_account - blob scanned and result imported to LAW
    Given API connections for logic app "sandbox_storage_account" are authorized
    When I trigger logic app "sandbox_storage_account" and wait for completion
    Then the logic app run status is "Succeeded"
    And within 15 minutes table "RecordedFutureSandboxResults_V2_CL" has a row where "Source" equals "StorageAccount" with non-empty columns "FileName, SandboxScore, HtmlReport, ScanTime"
