## 1. RecordedFuture-Playbook-Alert-Importer

- [ ] 1.1 Add `"identity": { "type": "SystemAssigned" }` to the Logic App resource in `Solutions/Recorded Future/Playbooks/Alerts/RecordedFuture-Playbook-Alert-Importer/azuredeploy.json`
- [ ] 1.2 Add `workspaceResourceId`, `workspaceName`, and `tableName` (default: `RecordedFuturePlaybookAlerts_V2_CL`) parameters; remove `workspaceId` and `workspaceKey` parameters
- [ ] 1.3 Add DCE resource (`Microsoft.Insights/dataCollectionEndpoints`) with `publicNetworkAccess: Enabled`
- [ ] 1.4 Add DCR resource (`Microsoft.Insights/dataCollectionRules`) with `RecordedFuturePlaybookAlerts_V2_CL` stream declaration (11 columns per PLAN.md) and correct `dependsOn` DCE
- [ ] 1.5 Add Log Analytics table resource (`Microsoft.OperationalInsights/workspaces/tables`) named `RecordedFuturePlaybookAlerts_V2_CL` with matching schema
- [ ] 1.6 Add role assignment (`Monitoring Metrics Publisher` role ID `3913510d-42f4-4e42-8a64-420c390055eb`) scoped to DCR, `dependsOn` DCR and Logic App
- [ ] 1.7 Add Logic App parameters `DceEndpoint`, `DcrImmutableId`, `StreamName` injected from ARM resource outputs
- [ ] 1.8 Replace `Send_Data` (`azureloganalyticsdatacollector` ApiConnection) action with `Http` action posting JSON array to Logs Ingestion API with ManagedServiceIdentity auth
- [ ] 1.9 Remove `azureloganalyticsdatacollector` connection parameter from `$connections` and its `Microsoft.Web/connections` resource
- [ ] 1.10 Bump `contentVersion` in the ARM template

## 2. RecordedFuture-Alert-Importer

- [ ] 2.1 Add `"identity": { "type": "SystemAssigned" }` to the Logic App resource in `Solutions/Recorded Future/Playbooks/Alerts/RecordedFuture-Alert-Importer/azuredeploy.json`
- [ ] 2.2 Add `workspaceResourceId`, `workspaceName`, and `tableName` (default: `RecordedFuturePortalAlerts_V2_CL`) parameters; remove `workspaceId` and `workspaceKey` parameters
- [ ] 2.3 Add DCE, DCR with `RecordedFuturePortalAlerts_V2_CL` schema (11 columns including 2 dynamic fields), Log Analytics table named `RecordedFuturePortalAlerts_V2_CL`, and role assignment resources
- [ ] 2.4 Add Logic App parameters `DceEndpoint`, `DcrImmutableId`, `StreamName` from ARM outputs
- [ ] 2.5 Replace `Send_Data_2` action with `Http` action; wrap the single-object body in a JSON array using `createArray(...)` expression
- [ ] 2.6 Remove `azureloganalyticsdatacollector` connection and resource
- [ ] 2.7 Bump `contentVersion`

## 3. RecordedFuture-ThreatMap-Importer

- [ ] 3.1 Add `"identity": { "type": "SystemAssigned" }` to Logic App in `Solutions/Recorded Future/Playbooks/ThreatHunting/RecordedFuture-ThreatMap-Importer/azuredeploy.json`
- [ ] 3.2 Add `workspaceResourceId`, `workspaceName`, and `tableName` (default: `RecordedFutureThreatMap_V2_CL`) parameters; remove legacy params
- [ ] 3.3 Add DCE, DCR with `RecordedFutureThreatMap_V2_CL` schema (`TimeGenerated`, `id`, `name`, `intent`, `opportunity`, `alias`, `categories`, `log_entries`), Log Analytics table named `RecordedFutureThreatMap_V2_CL`, and role assignment
- [ ] 3.4 Add Logic App parameters `DceEndpoint`, `DcrImmutableId`, `StreamName` from ARM outputs
- [ ] 3.5 Replace `Send_Data_-_Save_full_ThreatMap_response` action with `Http` action (payload is already an array from the Parse_JSON step; verify and pass through)
- [ ] 3.6 Remove `azureloganalyticsdatacollector` connection and resource
- [ ] 3.7 Bump `contentVersion`

## 4. RecordedFuture-ThreatMapMalware-Importer

- [ ] 4.1 Add `"identity": { "type": "SystemAssigned" }` to Logic App in `Solutions/Recorded Future/Playbooks/ThreatHunting/RecordedFuture-ThreatMapMalware-Importer/azuredeploy.json`
- [ ] 4.2 Add `workspaceResourceId`, `workspaceName`, and `tableName` (default: `RecordedFutureThreatMapMalware_V2_CL`) parameters; remove legacy params
- [ ] 4.3 Add DCE, DCR with `RecordedFutureThreatMapMalware_V2_CL` schema (same as ThreatMap but with `prevalence` instead of `intent`), Log Analytics table named `RecordedFutureThreatMapMalware_V2_CL`, and role assignment
- [ ] 4.4 Add Logic App parameters `DceEndpoint`, `DcrImmutableId`, `StreamName` from ARM outputs
- [ ] 4.5 Replace `Send_Data_-_Save_full_ThreatMap_Malware_Response` action with `Http` action
- [ ] 4.6 Remove `azureloganalyticsdatacollector` connection and resource
- [ ] 4.7 Bump `contentVersion`

## 5. UI Definition and Migration Guide

- [ ] 5.1 Add `"Microsoft.Insights/dataCollectionEndpoints"` and `"Microsoft.Insights/dataCollectionRules"` to `resourceProviders` in `Solutions/Recorded Future/Package/createUiDefinition.json`
- [ ] 5.2 Create `Solutions/Recorded Future/MIGRATION_GUIDE.md` covering: what changed & why, new prerequisites, new `_V2_CL` table names, side-by-side upgrade path (old and new can run in parallel since they target different tables), KQL query update instructions, rollback instructions
