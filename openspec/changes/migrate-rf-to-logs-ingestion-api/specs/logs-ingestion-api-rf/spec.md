## ADDED Requirements

### Requirement: ARM template includes Logs Ingestion API infrastructure
Each of the 4 `Solutions/Recorded Future` playbook ARM templates SHALL include: a Data Collection Endpoint (`Microsoft.Insights/dataCollectionEndpoints`), a Data Collection Rule (`Microsoft.Insights/dataCollectionRules`), a Log Analytics Custom Table (`Microsoft.OperationalInsights/workspaces/tables`), and a role assignment granting the Logic App's system-assigned identity `Monitoring Metrics Publisher` on the DCR.

#### Scenario: Template deploys without azureloganalyticsdatacollector
- **WHEN** the ARM template is deployed to Azure
- **THEN** it creates a DCE, DCR, Log Analytics table, and role assignment without requiring a `workspaceId` shared key or `azureloganalyticsdatacollector` connection resource

#### Scenario: Logic App has system-assigned identity
- **WHEN** the ARM template deploys the Logic App resource
- **THEN** the Logic App's `identity.type` is `SystemAssigned`

#### Scenario: Role assignment enables ingestion
- **WHEN** the ARM template deployment completes
- **THEN** the Logic App's managed identity has `Monitoring Metrics Publisher` (role ID `3913510d-42f4-4e42-8a64-420c390055eb`) scoped to the DCR resource

---

### Requirement: Playbooks use HTTP action with Managed Identity to ingest data
Each playbook's data-send Logic App action SHALL use an `Http` action type posting a JSON array to the Logs Ingestion API endpoint, authenticated with `ManagedServiceIdentity` targeting `https://monitor.azure.com`.

#### Scenario: Playbook Alert Importer sends data via Logs Ingestion API
- **WHEN** `RecordedFuture-Playbook-Alert-Importer` executes the send-data step
- **THEN** it posts a JSON array to `{DceEndpoint}/dataCollectionRules/{DcrImmutableId}/streams/{StreamName}?api-version=2023-01-01` using Managed Identity auth

#### Scenario: Alert Importer wraps single object in array
- **WHEN** `RecordedFuture-Alert-Importer` executes the send-data step
- **THEN** it posts a single-element JSON array (wrapped via `createArray(...)`) to the Logs Ingestion API using Managed Identity auth

#### Scenario: ThreatMap Importer sends data via Logs Ingestion API
- **WHEN** `RecordedFuture-ThreatMap-Importer` executes the send-data step
- **THEN** it posts the threat actor array to the Logs Ingestion API using Managed Identity auth

#### Scenario: ThreatMapMalware Importer sends data via Logs Ingestion API
- **WHEN** `RecordedFuture-ThreatMapMalware-Importer` executes the send-data step
- **THEN** it posts the malware actor array to the Logs Ingestion API using Managed Identity auth

---

### Requirement: New _V2_CL tables provisioned with bare column names
All 4 playbooks SHALL target new `_V2_CL` table names. DCR stream declarations and Log Analytics table schemas SHALL use bare column names with no `_s`, `_d`, or `_b` suffixes.

#### Scenario: RecordedFuturePortalAlerts_V2_CL has correct schema
- **WHEN** the DCR for `RecordedFuturePortalAlerts_V2_CL` is created
- **THEN** its stream declarations include `TimeGenerated` (datetime), `RuleName` (string), `Triggered` (datetime), `AlertName` (string), `AlertID` (string), `URL` (string), `Document_url` (string), `AISummary` (string), `Fragment` (string), `Entity` (dynamic), `Documents` (dynamic)

#### Scenario: RecordedFuturePlaybookAlerts_V2_CL has correct schema
- **WHEN** the DCR for `RecordedFuturePlaybookAlerts_V2_CL` is created
- **THEN** its stream declarations include all 11 fields defined in PLAN.md with correct types and no `_s` suffixes

#### Scenario: RecordedFutureThreatMap_V2_CL has correct schema
- **WHEN** the DCR for `RecordedFutureThreatMap_V2_CL` is created
- **THEN** its stream declarations include `TimeGenerated` (datetime), `id` (string), `name` (string), `intent` (int), `opportunity` (int), `alias` (dynamic), `categories` (dynamic), `log_entries` (dynamic)

#### Scenario: RecordedFutureThreatMapMalware_V2_CL has correct schema
- **WHEN** the DCR for `RecordedFutureThreatMapMalware_V2_CL` is created
- **THEN** its stream declarations match `RecordedFutureThreatMap_V2_CL` except `prevalence` (int) replaces `intent`

---

### Requirement: Deploy parameters updated to remove shared key and add workspace resource ID
Each playbook ARM template SHALL remove `workspaceId` and `workspaceKey` parameters and add `workspaceResourceId` (full resource ID), `workspaceName`, and `tableName` (defaulting to the appropriate `_V2_CL` name) parameters.

#### Scenario: Template accepts workspaceResourceId instead of workspaceId/workspaceKey
- **WHEN** a user deploys the updated template
- **THEN** the required parameters include `workspaceResourceId` and `workspaceName`; `workspaceId` and `workspaceKey` are absent

#### Scenario: tableName defaults to the V2 table name
- **WHEN** a user deploys without specifying `tableName`
- **THEN** the DCR stream targets the `_V2_CL` table name for that playbook (e.g. `RecordedFuturePortalAlerts_V2_CL`)

---

### Requirement: createUiDefinition.json declares DCE and DCR resource providers
`Solutions/Recorded Future/Package/createUiDefinition.json` SHALL include `Microsoft.Insights/dataCollectionEndpoints` and `Microsoft.Insights/dataCollectionRules` in its `resourceProviders` array.

#### Scenario: Solution UI definition registers Insights resource providers
- **WHEN** a user deploys the solution via the Azure Marketplace or Solutions hub
- **THEN** the deployment does not fail due to unregistered resource providers for DCE/DCR

---

### Requirement: Migration guide documents upgrade path for Recorded Future solution
`Solutions/Recorded Future/MIGRATION_GUIDE.md` SHALL be created covering: what changed and why, new prerequisites, new `_V2_CL` table names, side-by-side upgrade path (old and new can run in parallel since they target different tables), KQL query update instructions, and rollback instructions.

#### Scenario: Existing customer can deploy new version without disrupting the old
- **WHEN** an existing customer follows the migration guide
- **THEN** they can deploy the new `_V2_CL`-based playbooks alongside the old ones, verify data flows, update their queries to point at the new table names, and decommission the old playbooks at their own pace
