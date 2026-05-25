## 0. Identity Proof-of-Concept (do first)

- [x] 0.1 Deploy a minimal test Logic App with `"identity": { "type": "SystemAssigned" }`, a DCE, a DCR, a Log Analytics table, and a `Monitoring Metrics Publisher` role assignment to the `rf-erik` resource group using `ErikLogAnalyticWorkspace` — use a throw-away name (e.g. `rfi-identity-poc`)
- [x] 0.2 Manually trigger the Logic App with a hardcoded test payload and verify the HTTP action succeeds (status 204) against the Logs Ingestion API
- [x] 0.3 Confirm data appears in the target `_V2_CL` table via KQL in Log Analytics
- [x] 0.4 If system-assigned identity does NOT work (e.g. role assignment race, propagation delay): evaluate user-assigned managed identity as fallback and update design decision D2 accordingly
- [x] 0.5 Tear down the POC resources after validation

**POC results (2026-05-25):** ✅ System-assigned identity works. HTTP action returned 204 NoContent. Record confirmed in KQL (~3 min ingestion lag). No fallback needed.

**ARM template finding:** `streamDeclarations` property keys must be **literal strings** — ARM expressions (e.g. `"[variables('StreamName')]"`) are not allowed as object key names. All playbook templates must hard-code the stream name key (e.g. `"Custom-RecordedFutureIdentity_PlaybookAlertResults_V2_CL"`).

## 1. RFI-Playbook-Alert-Importer-LAW

- [ ] 1.1 Add `"identity": { "type": "SystemAssigned" }` to Logic App in `Solutions/Recorded Future Identity/Playbooks/RFI-Playbook-Alert-Importer-LAW/azuredeploy.json`
- [ ] 1.2 Add `workspaceResourceId` (for DCR `destinations.logAnalytics`) and `tableName` (default: `RecordedFutureIdentity_PlaybookAlertResults_V2_CL`) parameters; retain existing `log_analytics_workspace_name` parameter as-is
- [ ] 1.3 Add DCE resource (`Microsoft.Insights/dataCollectionEndpoints`) with `publicNetworkAccess: Enabled`
- [ ] 1.4 Add DCR with 47-column `RecordedFutureIdentity_PlaybookAlertResults_V2_CL` schema (per PLAN.md) and correct `dependsOn` DCE
- [ ] 1.5 Add Log Analytics table resource named `RecordedFutureIdentity_PlaybookAlertResults_V2_CL` with matching schema
- [ ] 1.6 Add role assignment (`Monitoring Metrics Publisher` role ID `3913510d-42f4-4e42-8a64-420c390055eb`) scoped to DCR, `dependsOn` DCR and Logic App
- [ ] 1.7 Add Logic App parameters `DceEndpoint`, `DcrImmutableId`, `StreamName` injected from ARM resource outputs
- [ ] 1.8 Remove `Check_if_table_exists` and `Create_table_if_missing` Logic App actions
- [ ] 1.9 Replace send-data action with `Http` action posting JSON array to Logs Ingestion API with ManagedServiceIdentity auth; ensure body is an array
- [ ] 1.10 Remove `azureloganalyticsdatacollector` connection parameter from `$connections` and its `Microsoft.Web/connections` resource
- [ ] 1.11 Bump `contentVersion` minor (e.g. `1.0.0.0` → `1.1.0.0`)
- [ ] 1.12 Test-deploy to `rf-erik` resource group with a unique name (e.g. `rfi-alert-importer-law-test`) using `az deployment group create`
- [ ] 1.13 Trigger a test run via `az logic workflow trigger run` and verify the run succeeds in Logic App run history
- [ ] 1.14 Confirm records appear in `RecordedFutureIdentity_PlaybookAlertResults_V2_CL` via KQL
- [ ] 1.15 Tear down test resources

## 2. RFI-Playbook-Alert-Importer-LAW-Sentinel

- [ ] 2.1 Add `"identity": { "type": "SystemAssigned" }` to Logic App in `Solutions/Recorded Future Identity/Playbooks/RFI-Playbook-Alert-Importer-LAW-Sentinel/azuredeploy.json`
- [ ] 2.2 Add `workspaceResourceId` (for DCR `destinations.logAnalytics`) and `tableName` (default: `RecordedFutureIdentity_PlaybookAlertResults_V2_CL`) parameters; retain existing `sentinel_workspace_name` parameter as-is
- [ ] 2.3 Add DCE, DCR with same 47-column `RecordedFutureIdentity_PlaybookAlertResults_V2_CL` schema as task 1.4, Log Analytics table, and role assignment
- [ ] 2.4 Add Logic App parameters `DceEndpoint`, `DcrImmutableId`, `StreamName` from ARM outputs
- [ ] 2.5 Replace send-data action with `Http` action posting JSON array to Logs Ingestion API with ManagedServiceIdentity auth
- [ ] 2.6 Remove `azureloganalyticsdatacollector` connection and resource
- [ ] 2.7 Bump `contentVersion` minor (e.g. `1.0.0.0` → `1.1.0.0`)
- [ ] 2.8 Test-deploy to `rf-erik` resource group with a unique name, trigger a test run, confirm records in `RecordedFutureIdentity_PlaybookAlertResults_V2_CL`, tear down

## 3. RFI-search-workforce-user

- [ ] 3.1 Add `"identity": { "type": "SystemAssigned" }` to Logic App in `Solutions/Recorded Future Identity/Playbooks/v3.0/RFI-search-workforce-user/azuredeploy.json`
- [ ] 3.2 Add `workspaceResourceId` (for DCR `destinations.logAnalytics`), `credDumpsTableName` (default: `RecordedFutureIdentity_LeakedCredentials_CredentialDumps_V2_CL`), and `malwareLogsTableName` (default: `RecordedFutureIdentity_LeakedCredentials_MalwareLogs_V2_CL`) parameters; retain existing `workspace_name` parameter as-is
- [ ] 3.3 Add DCE resource
- [ ] 3.4 Add DCR #1 for `CredentialDumps_V2_CL` with 2-column schema (`TimeGenerated`, `email`); add corresponding Log Analytics table `RecordedFutureIdentity_LeakedCredentials_CredentialDumps_V2_CL`
- [ ] 3.5 Add DCR #2 for `MalwareLogs_V2_CL` with 3-column schema (`TimeGenerated`, `login`, `domain`); add corresponding Log Analytics table `RecordedFutureIdentity_LeakedCredentials_MalwareLogs_V2_CL`
- [ ] 3.6 Add two role assignments (one per DCR) for Managed Identity
- [ ] 3.7 Add Logic App parameters for DCE endpoint, both DCR immutable IDs, and both stream names from ARM outputs
- [ ] 3.8 Replace `azureloganalyticsdatacollector` send actions with two `Http` actions targeting the correct DCR streams
- [ ] 3.9 Update KQL queries: replace table names `CredentialDumps_CL` → `CredentialDumps_V2_CL` and `MalwareLogs_CL` → `MalwareLogs_V2_CL`; replace `email_s` → `email`, `login_s` → `login`, `domain_s` → `domain`
- [ ] 3.10 Remove `azureloganalyticsdatacollector` connection and resource
- [ ] 3.11 Bump `contentVersion` minor (e.g. `1.0.0.0` → `1.1.0.0`)
/- [ ] 3.12 Test-deploy to `rf-erik` resource group with a unique name, trigger a test run, confirm records appear in both `CredentialDumps_V2_CL` and `MalwareLogs_V2_CL`, tear down

## 4. RFI-search-external-user

- [ ] 4.1 Add `"identity": { "type": "SystemAssigned" }` to Logic App in `Solutions/Recorded Future Identity/Playbooks/v3.0/RFI-search-external-user/azuredeploy.json`
- [ ] 4.2 Add `workspaceResourceId` (for DCR `destinations.logAnalytics`) and `tableName` (default: `RecordedFutureIdentity_LeakedCredentials_MalwareLogs_V2_CL`) parameters; retain existing `workspace_name` parameter as-is
- [ ] 4.3 Add DCE, DCR for `MalwareLogs_V2_CL` with 3-column schema (`TimeGenerated`, `login`, `domain`), Log Analytics table named `RecordedFutureIdentity_LeakedCredentials_MalwareLogs_V2_CL`, and role assignment
- [ ] 4.4 Add Logic App parameters `DceEndpoint`, `DcrImmutableId`, `StreamName` from ARM outputs
- [ ] 4.5 Replace `azureloganalyticsdatacollector` send action with `Http` action targeting Logs Ingestion API
- [ ] 4.6 Update KQL query: replace table name `MalwareLogs_CL` → `MalwareLogs_V2_CL`; replace `login_s` → `login`, `domain_s` → `domain`
- [ ] 4.7 Remove `azureloganalyticsdatacollector` connection and resource
- [ ] 4.8 Bump `contentVersion` minor (e.g. `1.0.0.0` → `1.1.0.0`)
- [ ] 4.9 Test-deploy to `rf-erik` resource group with a unique name, trigger a test run, confirm records appear in `MalwareLogs_V2_CL`, tear down

## 5. RFI-lookup-and-save-user

- [ ] 5.1 Add `"identity": { "type": "SystemAssigned" }` to Logic App in `Solutions/Recorded Future Identity/Playbooks/v3.0/RFI-lookup-and-save-user/azuredeploy.json`
- [ ] 5.2 Add `workspaceResourceId` (for DCR `destinations.logAnalytics`) and `tableName` (default: `RecordedFutureIdentity_UsersLookupResults_V2_CL`) parameters; `RFI-lookup-and-save-user` has no existing workspace name parameter to retain
- [ ] 5.3 Add DCE, DCR for `UsersLookupResults_V2_CL` with 4-column schema (`TimeGenerated`, `count` int, `next_offset` string, `identities` dynamic), Log Analytics table named `RecordedFutureIdentity_UsersLookupResults_V2_CL`, and role assignment
- [ ] 5.4 Add Logic App parameters `DceEndpoint`, `DcrImmutableId`, `StreamName` from ARM outputs
- [ ] 5.5 Remove runtime dynamic table name logic (the `triggerBody()?['lookup_results_log_analytics_custom_log_name']` reference)
- [ ] 5.6 Restructure the send-data action body: extract top-level scalars (`count`, `next_offset`) and pass `identities` as dynamic; wrap in a single-element array using `createArray(...)`
- [ ] 5.7 Replace `azureloganalyticsdatacollector` send action with `Http` action targeting Logs Ingestion API with ManagedServiceIdentity auth
- [ ] 5.8 Remove `azureloganalyticsdatacollector` connection and resource
- [ ] 5.9 Bump `contentVersion` minor (e.g. `1.0.0.0` → `1.1.0.0`)
- [ ] 5.10 Test-deploy to `rf-erik` resource group with a unique name, trigger a test run, confirm records appear in `UsersLookupResults_V2_CL` with correct `count`, `next_offset`, and `identities` columns, tear down

## 6. Migration Guide and Documentation

- [ ] 6.1 Create `Solutions/Recorded Future Identity/MIGRATION_GUIDE.md` covering: what changed & why, new prerequisites, new `_V2_CL` table names and bare column names, side-by-side upgrade path (old and new run in parallel targeting different tables), KQL query update instructions (`_s` column rename + table name rename), rollback instructions
- [ ] 6.2 Update `Solutions/Recorded Future Identity/Playbooks/readme.md` to reflect new deployment parameters and removed workspace key requirement
- [ ] 6.3 Update `Solutions/Recorded Future Identity/Playbooks/v3.0/readme.md` to reflect changes for v3.0 playbooks
