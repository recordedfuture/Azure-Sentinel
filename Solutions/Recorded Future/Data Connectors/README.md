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

### `RecordedFuture_PlaybookAlerts_ccf/` (preview)
Codeless Connector Framework (CCF) connector for playbook alerts, replacing the
`RecordedFuture-Playbook-Alert-Importer` Logic App.
- `RecordedFuture_PlaybookAlerts_ConnectorDefinition.json`: the `RecordedFuturePlaybookAlertsCCF`
  tile (`kind: Customizable`, API token, optional categories/priorities/statuses, connect toggle).
- `RecordedFuture_PlaybookAlerts_PollerConfig.json`: the `RestApiPoller` (`GET /gw/azure/playbook-alert/export`,
  `X-RFToken`, 60-minute window on `updated_from`/`updated_until`, offset paging `from`/`limit`=100).
- `azuredeploy_RecordedFuture_PlaybookAlerts_ccf.json`: standalone template that deploys the tile and an
  active poller directly, for manual testing without Content Hub.

The poller has no DCR or table of its own: it writes to stream `Custom-RecordedFuturePlaybookAlerts_V2_CL`
of the existing `recorded-future-dcr-playbook-alerts` DCR via `recorded-future-dce` (both from `azuredeploy.json`),
looked up by name in the workspace resource group when the connector is connected. It is a separate tile
because the packaged **Recorded Future - Log Ingestion** tile is a legacy `GenericUI` connector, which cannot
host a CCF connect toggle. Its entries in `../Package/mainTemplate.json` were added by hand; it is not in
`../Data/Solution_RecordedFuture.json` because the packaging tool expects CCF folders to contain their own DCR and table files.

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

