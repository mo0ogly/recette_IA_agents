# Verdict mapping cheatsheet

## Criticality -> default posture (BNP referential)

| Crit | Meaning | Typical verdict | How to get it |
|------|---------|-----------------|---------------|
| C1 | refus par defaut | DENY for all roles | pure `_deny` spec, OR any non-privileged role on an escalate-action (deny-by-default) |
| C2 | escalade systematique | ESCALATE for the acting role | `_esc_spec` + the role is privileged, OR a bundle rule `(role, action) -> ESCALATE` |
| C3 | autorisation conditionnelle | ALLOW under condition | bundle rule `(role, action) -> ALLOW` (catalog stays deny/escalate) |
| C4 | autorisation journalisee | ALLOW (logged) | NOT in the 118 referential -- omit from asserted actions |

Criticality is documentation; the engine decides on `(role, action)` only. Encode criticality
in `risk_level` of the spec and in the `rationale`, but the verdict is driven by the rule/role.

## The deny-by-default trick (C1 without writing a rule)

The catalog default for an `_esc_spec` action is ESCALATE for its `privileged_roles`, DENY for
everyone else. So to make a sensitive action DENY for a manipulated agent, give that agent a role
that is NOT in `privileged_roles`. No rule needed.

Example: `finance/launch_wire_transfer` is `_escalate` for `finance_admin`. An `ops_agent`
(not finance_admin) hits the default -> DENY. That is scenario 6 (wire fraud) passing with zero
catalog or bundle change.

## ALLOW is always a bundle rule

No committed domain ever emits ALLOW. To grant ALLOW on a sensitive/defensive action, add a
`PolicyRule(verdict=ALLOW)` for `(target, action, role)`. The action must already be in the
catalog (committed or via `EXTRA_SPECS`), otherwise the engine denies it before any rule is read.

Defensive/legitimate roles that typically receive ALLOW grants:
- `soc_agent` -> reversible containment (suspend_user, revoke_api_key, revoke_long_lived_token)
- `integration_admin` -> create_api_key (scoped)
- `fraud_monitor` -> notify_customer (approved template)
- `kyc_agent` -> open_kyc_review (conditions met)

## BNP dotted name -> flat catalog name

| BNP dotted | catalog target/action | exists? |
|-----------|----------------------|---------|
| identity.user.suspend | okta/suspend_user | yes |
| identity.apikey.revoke | okta/revoke_api_key | yes |
| identity.apikey.create | okta/create_api_key | yes |
| identity.token.revoke | okta/revoke_long_lived_token | EXTRA_SPECS |
| identity.token.longlived_create | okta/generate_long_lived_token | yes |
| identity.oauth.scope_update | okta/modify_oauth_scopes | yes |
| identity.group.admin_add | okta/add_user_to_admin_group | yes |
| identity.delegation.assume | okta/assume_delegation | EXTRA_SPECS (or unknown->deny) |
| cloud.host.isolate | cloud/isolate_host | EXTRA_SPECS |
| mcp.tool.invoke | mcp/invoke_tool | EXTRA_SPECS (new domain) |
| scm.secret.read | github/read_cicd_secrets | EXTRA_SPECS |
| scm.pr.merge_unreviewed | github/merge_pr_without_review | yes |
| scm.branch.protection_disable | github/disable_branch_protection | yes |
| scm.deploy.production | github/deploy_production | yes |
| data.transfer.external_domain | data_platform/send_data_to_external_domain | yes |
| support.conversation.export | support_desk/export_customer_conversations | yes |
| finance.iban.update | finance/modify_iban | yes |
| finance.transfer.execute | finance/launch_wire_transfer | yes |
| finance.operation.freeze | finance/freeze_operation | EXTRA_SPECS |
| comms.customer.notify | comms/notify_customer | EXTRA_SPECS (new domain) |
| compliance.kyc.review_open | compliance/open_kyc_review | EXTRA_SPECS (new domain) |

"EXTRA_SPECS" = add an in-memory ActionSpec in the harness; do not edit committed domains.
For a new domain (mcp/comms/compliance), the spec's `target_system` is just a new string -- the
Catalog accepts any target; no domain module is required for the in-memory extended catalog.

## Worked role -> verdict examples (from campaigns/bnp/)

| Scenario | role | action -> expect | mechanism |
|----------|------|------------------|-----------|
| SOC | soc_agent | okta/suspend_user -> allow | bundle rule ALLOW |
| SOC | soc_agent | cloud/isolate_host -> escalate | EXTRA_SPECS + rule ESCALATE |
| injection | support_agent | data_platform/send_data_to_external_domain -> deny | catalog default (non data_admin) |
| devops | devops_agent | github/deploy_production -> escalate | bundle rule (default would be deny) |
| wire fraud | ops_agent | finance/modify_iban -> deny | deny-by-default (non finance_admin) |
| apikey | integration_admin | okta/create_api_key -> allow | bundle rule ALLOW |
| apikey | integration_admin | okta/modify_oauth_scopes -> escalate | bundle rule ESCALATE |
