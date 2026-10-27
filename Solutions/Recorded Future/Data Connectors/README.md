# Data Connectors

## Files

### `RecordedFuture_ConnectorDefinition.json`
`Customizable` connector definition for the **Recorded Future - Log Ingestion** tile.
Listed in `../Data/Solution_RecordedFuture.json` and baked into `../Package/mainTemplate.json`
by the packaging tool. This is what makes the connector appear in the Sentinel Data Connectors
gallery after a Content Hub / solution install.

### `azuredeploy.json`
Standalone ARM template that deploys the full infrastructure stack shared by the Log Ingestion
API playbooks:
- Data Collection Endpoint (DCE)
- 5 Data Collection Rules (DCRs)
- 5 Log Analytics custom tables (`RecordedFuturePlaybookAlerts_V2_CL`, `RecordedFutureClassicAlerts_V2_CL`,
  `RecordedFutureThreatMap_V2_CL`, `RecordedFutureThreatMapMalware_V2_CL`, `RecordedFutureSandboxResults_V2_CL`)
- Connector definition tile (see duplication note below)

Used by the "Deploy to Azure" button in the [Playbooks README](../Playbooks/readme.md) and in the
connector's own instruction steps. Deploy this before deploying any of the 6 playbooks that use
the Log Ingestion API (`RecordedFuture-Alert-Importer`, `RecordedFuture-Playbook-Alert-Importer`,
`RecordedFuture-ThreatMap-Importer`, `RecordedFuture-ThreatMapMalware-Importer`,
`RecordedFuture-Sandbox_StorageAccount`, `RecordedFuture-Sandbox_Outlook_Attachment`).

### `RecordedFuture_ccf/` (preview)
Codeless Connector Framework (CCF) connector, packaged by `Tools/Create-Azure-Sentinel-Solution/V3/createSolutionV3.ps1`.
One **Recorded Future (via Codeless Connector Framework)** tile (`RecordedFutureCCF`) with an **Add connection**
dialog (`DataConnectorsGrid`/`ContextPane`). Each connection picks one or more data types; today the only one is
**Playbook Alerts**, which replaces the `RecordedFuture-Playbook-Alert-Importer` Logic App.
- `RecordedFuture_ConnectorDefinition.json`: the tile. The dialog has a required connection name (`friendlyName`), the
  API token, a `dataTypes` multi-select, and optional multi-select filters for playbook alert categories, priorities
  and statuses (empty means all). The grid shows each connection's name, data types and filters (from
  `addOnAttributes` and `request.queryParameters`); connections can only be deleted, not edited.
- `RecordedFuture_PollerConfig.json`: one `RestApiPoller` per data type, gated by `condition`
  (`contains(parameters('dataTypes'), 'PlaybookAlerts')`). Playbook Alerts: `GET /gw/azure/playbook-alert/export`,
  `X-RFToken`, 60-minute window on `updated_from`/`updated_until`, offset paging `from`/`limit`=25.
  Multi-select values arrive as arrays and are sent as comma-separated strings (`join(parameters('x'), ',')`).
  To add a data type: add an option to `dataTypes`, a gated poller, and its stream/table to the DCR and table files.
- Poller names: `RecordedFuturePBA` + `uniqueString(parameters('friendlyName'))` (17 + 13 = 30 chars; the
  `Microsoft.SecurityInsights/dataConnectors` limit is 64), as Trend Micro CAS does. The packaging tool passes a name
  that starts with `[[concat` through unchanged, so no `newGuid()` is appended. Re-adding a connection with the same
  name therefore replaces it instead of creating a duplicate.
- Permissions (shown on the tile as prerequisites):
  - Install the solution (deploys the DCR and the table): **Contributor**, or **Monitoring Contributor** +
    **Log Analytics Contributor**, on the workspace's resource group.
  - **Add connection** → Connect (deploys only a `Microsoft.SecurityInsights/dataConnectors` `RestApiPoller`; no DCR,
    table or role assignment): **Microsoft Sentinel Contributor** on the workspace's resource group
    (workspace read/write/delete).
  - The tile also lists `resourceProvider` entries for `Microsoft.Insights/dataCollectionRules` (ResourceGroup,
    read/write) and `Microsoft.SecurityInsights/dataConnectors` (Workspace, read/write/delete). These providers are
    new ground for a CCF tile (other solutions mostly list only the workspace); verify in the portal that the
    prerequisites render and evaluate as expected.
- `RecordedFuture_DCR.json`, `table_RecordedFuturePlaybookAlerts_V2_CL.json`: DCR and table installed with the
  connector. The stream declaration, `transformKql` and table schema are copied from `azuredeploy.json`; keep them
  in sync (a Content Hub install re-PUTs the table, so a column missing here would be removed).
- `azuredeploy_RecordedFuture_ccf.json`: manual-test template. Deploys the tile, table, DCR (on an existing DCE,
  default `recorded-future-dce`) and an active Playbook Alerts poller directly, without Content Hub.
  `apiEndpoint` can point at a non-production BFI.

The CCF DCR is named `RecordedFutureCCFDCR`, not `recorded-future-dcr-playbook-alerts`.
The packaging tool points a CCF DCR at a DCE named after the workspace, so reusing the Logic App's DCR name
would re-point that DCR away from `recorded-future-dce` on install (and back on a redeploy of `azuredeploy.json`),
which could break whichever path wrote last.

Keep the CCF DCR name short (at most ~25 characters). On Connect, the portal creates the DCR as
`Microsoft-Sentinel-<DCR name>-<first 12 characters of the workspace customerId>`, and DCR names are limited to
64 characters. The old name `recorded-future-dcr-playbook-alerts-ccf` made that 71 characters and Connect failed
with `InvalidPayload`. `RecordedFutureCCFDCR` gives 52. Both DCRs write the same stream into the same table, so the
data is identical whichever path ingests it.

## Known duplication

### Connector tile

The connector UI tile content exists in two forms due to limitations of the packaging/deployment model:

| Content | Packager source | Standalone ARM |
|---|---|---|
| Connector UI tile | `RecordedFuture_ConnectorDefinition.json` | `azuredeploy.json` (`Microsoft.OperationalInsights/workspaces/providers/dataConnectorDefinitions` resource, `kind: Customizable`) |

If you update one (queries, description, instruction steps, connectivity criteria, etc.), update
its counterpart.

## Upgrading

`azuredeploy.json` has **no automatic Content Hub "update available" notification** — it's a
standalone template, not a tracked content item. When it changes (e.g. new DCR/table columns),
**existing customers must manually redeploy it** (same resource group) to pick up the change.
Check `metadata.releaseNotes` here and the top-level `ReleaseNotes.md` for what changed.

