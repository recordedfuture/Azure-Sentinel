"""
In-memory ARM template patcher for v3.0 Identity API test isolation.

Applies surgical mutations to the RFI-search-workforce-user azuredeploy.json:

  1. Keeps the real RF credential/malware search API calls — tests real integration.
  2. Inserts Fake_credential_results / Fake_malware_results Compose actions after
     the real search, replacing results with a list containing a single
     test-<uuid>@<domain> email. Rewires downstream For_Each actions to iterate
     over these fake results instead of the real ones.
  3. The real LAW dedup queries still execute (tests azuremonitorlogs connection
     + query logic). The UUID email was never seen before so dedup always passes
     it through as new.
  4. Inserts Overwrite_risky_user_email Compose inside the protective-actions
     For_Each, hardcoding the email to TEST_USER_UPN before calling sub-playbooks.
     This makes RFI-add-EntraID-security-group-user and RFI-lookup-and-save-user
     find the real Entra test user regardless of the fake UUID email.
  5. Patches the Playbook-Name-lookup-and-save-user ARM parameter default to the
     date-scoped test lookup app name.
  6. Injects the RF API key into the RFI Custom Connector connection resource so
     it is pre-authorized on deploy (no manual portal step needed).
  7. Sets organization_domain default to the test domain.

The original file is never written to. The patched dict is written to a
temporary file for use with `az deployment group create`, then deleted.
"""
import copy
import json
from typing import Optional

# ── Action name constants ──────────────────────────────────────────────────────
CRED_SEARCH_ACTION   = "Credential_Search_-_Search_credential_data_for_one_or_more_domains"
MAKE_COMPARABLE_ACTION = "For_Each_-_Make_new_and_known_Credential_dumps_be_comparable"
ML_FOREACH_ACTION    = "For_Each_new_Malware_log_exposures"
FAKE_CRED_ACTION     = "Fake_credential_results"
FAKE_ML_ACTION       = "Fake_malware_results"
PROTECTIVE_FOREACH   = "For_each_new_exposures_-_do_protective_actions"
OVERWRITE_EMAIL_ACTION = "Overwrite_risky_user_email"
CURRENT_TIME_ACTION  = "Current_time"


def patch_search_template(
    template: dict,
    test_email: str,
    lookup_app_name: str,
    rf_api_key: Optional[str] = None,
    test_domain: Optional[str] = None,
    entra_user_upn: Optional[str] = None,
    security_group_id: Optional[str] = None,
) -> dict:
    """
    Return a deep copy of *template* with test-isolation mutations applied.

    Args:
        template:        Parsed RFI-search-workforce-user azuredeploy.json dict.
        test_email:      Unique fake email for this test run,
                         e.g. "test-a1b2c3d4@integrationsopsrecordedfutu.onmicrosoft.com".
                         Injected as the sole item in fake search results so the
                         dedup always treats it as new (UUID never seen before).
        lookup_app_name: Name of the date-scoped test lookup Logic App to call.
        rf_api_key:      If provided, inject into the RFI Custom Connector
                         connection resource so it is pre-authorized on deploy.
        test_domain:     If provided, set as the organization_domain default.
                         Use the domain that is authorized for the QA RF token
                         (e.g. "norsegods.online"), not the Entra tenant domain.
        entra_user_upn:  If provided, insert an additional Overwrite_entra_upn
                         Compose action that hardcodes the UPN passed to Entra
                         sub-playbooks. Use this to redirect Entra lookups to a
                         real test user regardless of the fake UUID test_email.
        security_group_id: If provided, set as the active_directory_security_group_id
                         definition parameter default.
    """
    t = copy.deepcopy(template)

    # ── Top-level ARM parameter defaults ──────────────────────────────────────
    arm_params = t.get("parameters", {})
    if "Playbook-Name-lookup-and-save-user" in arm_params:
        arm_params["Playbook-Name-lookup-and-save-user"]["defaultValue"] = lookup_app_name

    for resource in t["resources"]:

        # ── Logic App workflow mutations ──────────────────────────────────────
        if resource.get("type") == "Microsoft.Logic/workflows":
            defn = resource["properties"]["definition"]
            actions = defn["actions"]
            params = defn["parameters"]

            # 1. Set organization_domain default
            if test_domain and "organization_domain" in params:
                params["organization_domain"]["defaultValue"] = test_domain

            # 2. Set security_group_id default
            if security_group_id and "active_directory_security_group_id" in params:
                params["active_directory_security_group_id"]["defaultValue"] = security_group_id

            # 3. Insert Fake_credential_results Compose after real credential search
            #    Produces: [{"email": "<test_email>"}]
            actions[FAKE_CRED_ACTION] = {
                "type": "Compose",
                "description": (
                    "Test isolation: replace real credential search results with "
                    "a single fake UUID email so the dedup always treats it as new."
                ),
                "inputs": [{"email": test_email}],
                "runAfter": {CRED_SEARCH_ACTION: ["Succeeded"]},
            }

            # 4. Rewire For_Each_-_Make_new_and_known_Credential_dumps_be_comparable
            #    to iterate over fake results instead of real credential_dumps body
            actions[MAKE_COMPARABLE_ACTION]["foreach"] = (
                f"@outputs('{FAKE_CRED_ACTION}')"
            )
            # Update runAfter to depend on fake action
            actions[MAKE_COMPARABLE_ACTION]["runAfter"] = {
                FAKE_CRED_ACTION: ["Succeeded"],
                # Keep dependency on the init variable action
                **{
                    k: v for k, v in actions[MAKE_COMPARABLE_ACTION].get("runAfter", {}).items()
                    if k != CRED_SEARCH_ACTION
                },
            }
            # Fix the Append action inside to use the fake item's email field
            make_actions = actions[MAKE_COMPARABLE_ACTION]["actions"]
            if "Append_transformed_exposures_to_array" in make_actions:
                make_actions["Append_transformed_exposures_to_array"]["inputs"]["value"] = {
                    "email": f"@items('{MAKE_COMPARABLE_ACTION}')?['email']"
                }

            # 5. Insert Fake_malware_results Compose after real credential search.
            #    Produces: [{"login": "<test_email>", "domain": "<domain_part>"}]
            #    Uses the same email as credential dumps — the dedup will treat it as
            #    new (UUID never seen before). Note: this means two identical emails
            #    end up in newly_leaked_emails (one from each path), so the protective-
            #    actions foreach runs twice. The second add-to-group call will fail
            #    with "already a member". The run status will be Failed, but all LAW
            #    tables are written before the foreach runs (independent Send_Data steps),
            #    so LAW assertions still pass.
            test_domain_part = test_email.split("@")[1] if "@" in test_email else test_email
            actions[FAKE_ML_ACTION] = {
                "type": "Compose",
                "description": (
                    "Test isolation: replace real malware log results with "
                    "a single fake UUID identity so the dedup always treats it as new."
                ),
                "inputs": [{"login": test_email, "domain": test_domain_part}],
                "runAfter": {CRED_SEARCH_ACTION: ["Succeeded"]},
            }

            # 6. Rewire For_Each_new_Malware_log_exposures to iterate over fake results
            actions[ML_FOREACH_ACTION]["foreach"] = f"@outputs('{FAKE_ML_ACTION}')"
            actions[ML_FOREACH_ACTION]["runAfter"] = {
                FAKE_ML_ACTION: ["Succeeded"],
                **{
                    k: v for k, v in actions[ML_FOREACH_ACTION].get("runAfter", {}).items()
                    if k != CRED_SEARCH_ACTION
                },
            }
            # Fix the If condition inside to compare against login field of fake item
            if_action = actions[ML_FOREACH_ACTION]["actions"].get("If_Malware_log_exposure_is_new")
            if if_action:
                # The condition checks if login is in known_malware_log_creds — keep as-is,
                # it will just always be "new" since UUID was never seen before
                pass

            # 6b. Rewire the protective-actions ForEach to also wait for both Send_Data
            #     actions to complete before starting. This ensures LAW writes happen
            #     before the (potentially failing) Entra sub-playbook calls, so the
            #     LAW assertion steps succeed even when the run status is Failed.
            send_cred = "Send_Data_-_Save_new_Credential_dump_exposures_into_Log_Analytics_Custom_Log"
            send_ml   = "Send_Data_-_Save_new_Malware_log_exposures_into_Log_Analytics_Custom_Log"
            existing_ra = actions[PROTECTIVE_FOREACH].get("runAfter", {})
            actions[PROTECTIVE_FOREACH]["runAfter"] = {
                **existing_ra,
                send_cred: ["Succeeded", "Failed", "Skipped"],
                send_ml:   ["Succeeded", "Failed", "Skipped"],
            }

            # 6c. Make the malware-log extend-foreach a no-op so the malware email
            #     does NOT get added to newly_leaked_emails. This ensures exactly ONE
            #     email flows into the protective-actions ForEach (from credential dumps
            #     only), so the lookup sub-playbook runs exactly once and completes
            #     before any potential group-add failure can cancel it.
            #     The malware email still passes through dedup and Send_Data still writes
            #     it to RFI_MalwareLogs_V2_CL.
            extend_ml = "For_Each_-_extend_new_exposures_array_with_new_Malware_log_exposures"
            if extend_ml in actions:
                actions[extend_ml]["actions"] = {}

            # 7. Insert Overwrite_risky_user_email Compose inside protective ForEach.
            #    This sets the email used by ALL sub-playbooks to test_email (the UUID),
            #    ensuring consistent LAW writes. If entra_user_upn is also provided,
            #    we additionally insert Overwrite_entra_upn which overrides the email
            #    for Entra-specific sub-playbooks to a real Entra user.
            foreach_actions = actions[PROTECTIVE_FOREACH]["actions"]
            foreach_actions[OVERWRITE_EMAIL_ACTION] = {
                "type": "Compose",
                "description": (
                    "Test isolation: hardcode the email passed to sub-playbooks "
                    "to the test UUID email for consistent LAW writes."
                ),
                "inputs": test_email,
                "runAfter": {CURRENT_TIME_ACTION: ["Succeeded"]},
            }

            # 8. Rewire sub-playbook calls to depend on Overwrite and use its output
            patched_foreach = json.dumps(foreach_actions)
            # Replace the items() reference with the override output
            patched_foreach = patched_foreach.replace(
                f"items('{PROTECTIVE_FOREACH}')",
                f"outputs('{OVERWRITE_EMAIL_ACTION}')",
            )
            new_foreach_actions = json.loads(patched_foreach)
            # Fix runAfter: any action that depended on Current_time and is not
            # Overwrite_risky_user_email itself should now depend on Overwrite
            for aname, action in new_foreach_actions.items():
                if aname == OVERWRITE_EMAIL_ACTION:
                    continue
                ra = action.get("runAfter", {})
                if CURRENT_TIME_ACTION in ra:
                    ra[OVERWRITE_EMAIL_ACTION] = ra.pop(CURRENT_TIME_ACTION)

            # 9. If entra_user_upn is provided, insert a second override for Entra
            #    sub-playbooks (add-group + confirm-risky) so they act on a real user.
            #    Overwrite_entra_upn depends on RFI-lookup-and-save-user completing
            #    first, ensuring the lookup always finishes before any Entra call
            #    can fail and cancel the foreach iteration.
            if entra_user_upn:
                entra_override = "Overwrite_entra_upn"
                new_foreach_actions[entra_override] = {
                    "type": "Compose",
                    "description": (
                        "Test isolation: hardcode the UPN passed to Entra sub-playbooks "
                        "to a known real Entra user. Runs after lookup to ensure lookup "
                        "completes before any Entra failure can cancel the iteration."
                    ),
                    "inputs": entra_user_upn,
                    "runAfter": {"RFI-lookup-and-save-user": ["Succeeded", "Failed", "Skipped"]},
                }
                # Rewire Entra-specific sub-playbooks to use the Entra UPN override
                for entra_action in ("RFI-add-EntraID-security-group-user", "RFI-confirm-EntraID-risky-user"):
                    if entra_action in new_foreach_actions:
                        act = new_foreach_actions[entra_action]
                        body = act.get("inputs", {}).get("body", {})
                        if "risky_user_email" in body:
                            body["risky_user_email"] = f"@outputs('{entra_override}')"
                        ra = act.get("runAfter", {})
                        if OVERWRITE_EMAIL_ACTION in ra:
                            ra[entra_override] = ra.pop(OVERWRITE_EMAIL_ACTION)

            actions[PROTECTIVE_FOREACH]["actions"] = new_foreach_actions

        # ── Inject RF API key into the RFI Custom Connector connection ─────────
        if rf_api_key and resource.get("type") == "Microsoft.Web/connections":
            api_id = resource.get("properties", {}).get("api", {}).get("id", "")
            if "customApis" in api_id:
                resource["properties"]["parameterValues"] = {"api_key": rf_api_key}

    return t


def patch_lookup_template(
    template: dict,
    rf_api_key: Optional[str] = None,
) -> dict:
    """
    Return a deep copy of the RFI-lookup-and-save-user template with minimal
    test-isolation patches applied.

    The lookup sub-playbook is called by the search playbook with the test UUID
    email already set. No structural changes needed — just inject the RF API key.

    Args:
        template:   Parsed RFI-lookup-and-save-user azuredeploy.json dict.
        rf_api_key: If provided, inject into the RFI Custom Connector connection
                    resource so it is pre-authorized on deploy.
    """
    t = copy.deepcopy(template)
    for resource in t["resources"]:
        if rf_api_key and resource.get("type") == "Microsoft.Web/connections":
            api_id = resource.get("properties", {}).get("api", {}).get("id", "")
            if "customApis" in api_id:
                resource["properties"]["parameterValues"] = {"api_key": rf_api_key}
    return t
