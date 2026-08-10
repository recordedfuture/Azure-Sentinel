"""
Sentinel suite deployment helpers.

Extracted from environment.py to keep lifecycle hooks readable.
"""
import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from support import az_client, config
from support.playbook_alert_patcher import patch_template as patch_pba
from support.alert_importer_patcher import patch_template as patch_alert
from rf_e2e_tests.patchers import write_temp


def _write_unpatched(template: dict) -> str:
    return write_temp(template)


def _deploy_one(key: str, context) -> str:
    params = copy.deepcopy(config.SCENARIO_PARAMS[key])
    template_path = {
        "playbook_alert_importer": config.TEMPLATE_PLAYBOOK_ALERT_IMPORTER,
        "alert_importer":          config.TEMPLATE_ALERT_IMPORTER,
        "threatmap":               config.TEMPLATE_THREATMAP_IMPORTER,
        "threatmap_malware":       config.TEMPLATE_THREATMAP_MALWARE_IMPORTER,
        "sandbox_storage_account": config.TEMPLATE_SANDBOX_STORAGE_ACCOUNT,
    }[key]

    with open(template_path) as f:
        template = json.load(f)

    if key == "playbook_alert_importer":
        tmp = write_temp(patch_pba(template, context.test_playbook_alert_id))
    elif key == "alert_importer":
        tmp = write_temp(patch_alert(template))
    else:
        # threatmap / threatmap_malware / sandbox_storage_account: no
        # alert-pinning patcher needed. ThreatMap playbooks send the full
        # current threat map as a single row per run (no per-alert filtering
        # to pin); the Sandbox StorageAccount playbook's blob path is already
        # hardcoded in the template itself (see
        # sandbox_client.ensure_sandbox_storage_fixture()), so no patch is
        # needed there either — deployed unpatched.
        tmp = _write_unpatched(template)

    try:
        az_client.deploy_logic_app(tmp, params)
    finally:
        os.unlink(tmp)
    return key


def deploy_all(keys: list, context) -> None:
    """Deploy all Logic Apps in *keys* in parallel."""
    print(f"\n=== Deploying test logic apps (parallel): {keys} ===")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_deploy_one, key, context): key for key in keys}
        for future in as_completed(futures):
            key = futures[future]
            try:
                future.result()
                print(f"  [deploy] {key} ready")
            except Exception as exc:
                print(f"  [deploy] {key} FAILED: {exc}")
                raise


_ANALYTIC_RULES_DIR = (
    config._SOLUTIONS / "Analytic Rules" / "IncidentCreation"
)


def deploy_analytic_rules() -> None:
    """
    Deploy and enable the NRT incident-creation analytic rules for both alert
    importers, read directly from the YAML source files.
    Idempotent — safe to call on every before_all.

    Rules must be active BEFORE data lands in the tables so NRT evaluation picks
    up the rows. Call this before deploying/triggering the Logic Apps.
    """
    print("\n=== Deploying analytic rules ===")
    az_client.deploy_analytic_rule_from_yaml(
        yaml_path=_ANALYTIC_RULES_DIR / "RecordedFuturePlaybookAlerts.yaml",
        rule_name="RecordedFuturePlaybookAlertsIncidentCreation",
    )
    az_client.deploy_analytic_rule_from_yaml(
        yaml_path=_ANALYTIC_RULES_DIR / "RecordedFutureAlerts.yaml",
        rule_name="RecordedFutureClassicAlertsIncidentCreation",
    )


def deploy_workbooks() -> list:
    """
    Deploy the ThreatHunting workbooks (ThreatActor + Malware), which consume
    the ThreatMap/ThreatMapMalware tables. Idempotent — safe to call on every
    before_all (each workbook has a fixed resource ID, see config.WORKBOOK_TEMPLATES).

    Returns a list of {key, display_name, resource_id} for each deployed
    workbook, for the after_all "open in browser?" prompt.
    """
    print("\n=== Deploying ThreatHunting workbooks ===")
    source_id = (
        f"/subscriptions/{config.SUBSCRIPTION_ID}/resourceGroups/{config.RESOURCE_GROUP}"
        f"/providers/Microsoft.OperationalInsights/workspaces/{config.LAW_NAME}"
    )
    deployed = []
    for key, wb in config.WORKBOOK_TEMPLATES.items():
        resource_id = az_client.deploy_workbook(
            json_path=wb["path"],
            workbook_id=wb["id"],
            display_name=wb["display_name"],
            source_id=source_id,
        )
        deployed.append({
            "key": key,
            "display_name": wb["display_name"],
            "resource_id": resource_id,
        })
    return deployed
