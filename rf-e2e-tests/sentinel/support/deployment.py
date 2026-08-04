"""
Sentinel suite deployment helpers.

Extracted from environment.py to keep lifecycle hooks readable.
"""
import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from support import az_client, config, rf_client
from support.playbook_alert_patcher import patch_template as patch_pba
from support.alert_importer_patcher import patch_template as patch_alert
from rf_e2e_tests.patchers import write_temp


def _write_unpatched(template: dict) -> str:
    from rf_e2e_tests.patchers import write_temp
    return write_temp(template)


def _deploy_one(key: str, context) -> str:
    params = copy.deepcopy(config.SCENARIO_PARAMS[key])
    template_path = {
        "playbook_alert_importer": config.TEMPLATE_PLAYBOOK_ALERT_IMPORTER,
        "alert_importer":          config.TEMPLATE_ALERT_IMPORTER,
        "threatmap":               config.TEMPLATE_THREATMAP_IMPORTER,
        "threatmap_malware":       config.TEMPLATE_THREATMAP_MALWARE_IMPORTER,
    }[key]

    with open(template_path) as f:
        template = json.load(f)

    if key == "playbook_alert_importer":
        tmp = write_temp(patch_pba(template, context.test_playbook_alert_id))
    elif key == "alert_importer":
        tmp = write_temp(patch_alert(template))
    else:
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
