## ADDED Requirements

### Requirement: ARM template includes Logs Ingestion API infrastructure for RFI playbooks
Each of the 5 `Solutions/Recorded Future Identity` playbook ARM templates SHALL include a Data Collection Endpoint, one or more Data Collection Rules (one per target table), corresponding Log Analytics Custom Tables, and role assignments granting each Logic App's system-assigned identity `Monitoring Metrics Publisher` on its DCR(s).

#### Scenario: RFI-Playbook-Alert-Importer-LAW deploys with Logs Ingestion infrastructure
- **WHEN** `RFI-Playbook-Alert-Importer-LAW` ARM template is deployed
- **THEN** it creates a DCE, DCR for `RecordedFutureIdentity_PlaybookAlertResults_V2_CL`, the Log Analytics table, and a role assignment; no workspace key or `azureloganalyticsdatacollector` connection is required

#### Scenario: RFI-Playbook-Alert-Importer-LAW-Sentinel deploys with Logs Ingestion infrastructure
- **WHEN** `RFI-Playbook-Alert-Importer-LAW-Sentinel` ARM template is deployed
- **THEN** it creates the same infrastructure as `RFI-Playbook-Alert-Importer-LAW`, targeting `RecordedFutureIdentity_PlaybookAlertResults_V2_CL`

#### Scenario: RFI-search-workforce-user deploys with two DCRs
- **WHEN** `RFI-search-workforce-user` ARM template is deployed
- **THEN** it creates a DCE, two DCRs (one each for `RecordedFutureIdentity_LeakedCredentials_CredentialDumps_V2_CL` and `RecordedFutureIdentity_LeakedCredentials_MalwareLogs_V2_CL`), two tables, and two role assignments

#### Scenario: RFI-search-external-user deploys with one DCR
- **WHEN** `RFI-search-external-user` ARM template is deployed
- **THEN** it creates a DCE, one DCR for `RecordedFutureIdentity_LeakedCredentials_MalwareLogs_V2_CL`, the table, and a role assignment

#### Scenario: RFI-lookup-and-save-user deploys with one DCR
- **WHEN** `RFI-lookup-and-save-user` ARM template is deployed
- **THEN** it creates a DCE, one DCR for `RecordedFutureIdentity_UsersLookupResults_V2_CL`, the table, and a role assignment

---

### Requirement: Seed actions removed from RFI-Playbook-Alert-Importer-LAW
The `Check_if_table_exists` and `Create_table_if_missing` Logic App actions SHALL be removed from `RFI-Playbook-Alert-Importer-LAW`. Table provisioning is handled declaratively by the ARM template.

#### Scenario: Playbook runs without table seed actions
- **WHEN** `RFI-Playbook-Alert-Importer-LAW` executes
- **THEN** it does not contain `Check_if_table_exists` or `Create_table_if_missing` action steps; the workflow proceeds directly to data ingestion

---

### Requirement: RFI playbooks use HTTP action with Managed Identity for data ingestion
All 5 RFI playbooks' data-send Logic App actions SHALL use an `Http` action posting a JSON array to the Logs Ingestion API, authenticated with `ManagedServiceIdentity` targeting `https://monitor.azure.com`.

#### Scenario: RFI-Playbook-Alert-Importer-LAW sends 47-field records
- **WHEN** the playbook processes an alert
- **THEN** it posts a JSON array of records matching the `RecordedFutureIdentity_PlaybookAlertResults_V2_CL` schema to the Logs Ingestion API

#### Scenario: RFI-search-workforce-user sends to two separate streams
- **WHEN** the playbook processes leaked credentials
- **THEN** it posts credential dump records to the `CredentialDumps_V2_CL` DCR stream and malware log records to the `MalwareLogs_V2_CL` DCR stream

#### Scenario: RFI-lookup-and-save-user sends UsersLookupResults
- **WHEN** the playbook processes a lookup response
- **THEN** it posts a JSON array with `count`, `next_offset`, and `identities` (dynamic) to the `RecordedFutureIdentity_UsersLookupResults_V2_CL` stream

---

### Requirement: KQL queries in RFI playbooks target new _V2_CL table names with bare column names
All KQL queries within `RFI-search-workforce-user` and `RFI-search-external-user` SHALL be updated to query the new `_V2_CL` table names and use bare column names (`email`, `login`, `domain`) instead of legacy suffixed names (`email_s`, `login_s`, `domain_s`).

#### Scenario: RFI-search-workforce-user queries target V2 tables with bare column names
- **WHEN** `RFI-search-workforce-user` executes KQL queries
- **THEN** the queries reference `RecordedFutureIdentity_LeakedCredentials_CredentialDumps_V2_CL` and `RecordedFutureIdentity_LeakedCredentials_MalwareLogs_V2_CL`, using columns `email`, `login`, and `domain`

#### Scenario: RFI-search-external-user queries target V2 table with bare column names
- **WHEN** `RFI-search-external-user` executes KQL queries
- **THEN** the queries reference `RecordedFutureIdentity_LeakedCredentials_MalwareLogs_V2_CL`, using columns `login` and `domain`

---

### Requirement: New _V2_CL tables provisioned with bare column names
All RFI DCR stream declarations and Log Analytics table schemas SHALL use `_V2_CL` table names and exact bare column names with correct types as defined in PLAN.md, with no `_s`/`_d`/`_b` suffixes.

#### Scenario: RecordedFutureIdentity_PlaybookAlertResults_V2_CL has 47-field schema
- **WHEN** the DCR for `RecordedFutureIdentity_PlaybookAlertResults_V2_CL` is created
- **THEN** its stream declarations include all 47 fields defined in PLAN.md, with `TimeGenerated` as datetime, boolean fields as boolean, datetime fields as datetime, and the remainder as string

#### Scenario: RecordedFutureIdentity_LeakedCredentials_CredentialDumps_V2_CL schema
- **WHEN** the DCR for `CredentialDumps_V2_CL` is created
- **THEN** its stream declarations include `TimeGenerated` (datetime) and `email` (string)

#### Scenario: RecordedFutureIdentity_LeakedCredentials_MalwareLogs_V2_CL schema
- **WHEN** the DCR for `MalwareLogs_V2_CL` is created
- **THEN** its stream declarations include `TimeGenerated` (datetime), `login` (string), and `domain` (string)

#### Scenario: RecordedFutureIdentity_UsersLookupResults_V2_CL schema
- **WHEN** the DCR for `UsersLookupResults_V2_CL` is created
- **THEN** its stream declarations include `TimeGenerated` (datetime), `count` (int), `next_offset` (string), and `identities` (dynamic)

---

### Requirement: RFI-lookup-and-save-user table name is a deploy-time parameter defaulting to _V2_CL
The `RFI-lookup-and-save-user` playbook SHALL expose a `tableName` parameter (defaulting to `RecordedFutureIdentity_UsersLookupResults_V2_CL`) fixed at deploy time in the DCR stream. Runtime dynamic table name override via trigger body SHALL be removed.

#### Scenario: Table name defaults to V2 canonical value at deploy time
- **WHEN** `RFI-lookup-and-save-user` is deployed without specifying `tableName`
- **THEN** the DCR stream targets `RecordedFutureIdentity_UsersLookupResults_V2_CL`

#### Scenario: Runtime table name override is no longer supported
- **WHEN** the playbook trigger body contains a `lookup_results_log_analytics_custom_log_name` field
- **THEN** the playbook ignores it and sends data to the table name configured at deploy time

---

### Requirement: Migration guide documents upgrade path for Recorded Future Identity solution
`Solutions/Recorded Future Identity/MIGRATION_GUIDE.md` SHALL be created covering: what changed and why, new prerequisites, new `_V2_CL` table names and bare column names, side-by-side upgrade path (old and new can run in parallel), KQL query update instructions, and rollback instructions.

#### Scenario: Existing RFI customer can deploy new version without disrupting the old
- **WHEN** an existing customer follows the RFI migration guide
- **THEN** they can deploy the new `_V2_CL`-based playbooks alongside the old ones, verify data flows, update their saved queries to point at the new table names and bare column names, and decommission the old playbooks at their own pace
