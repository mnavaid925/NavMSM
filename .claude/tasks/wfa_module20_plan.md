# Module 20 — Workflow & Business Process Automation — Implementation Plan

**App:** `apps/wfa/` · **URL prefix:** `/wfa/` · **Reference modules:** `apps/dms/` (most recent — same scale + 5-sub-module shape), `apps/iot/` (signal-driven cross-module dispatch), `apps/compliance/` (workflow/approval pattern).

**Confirmed scope (via /AskUserQuestion):**
- App slug: `wfa` · URL: `/wfa/`
- 20.1 BPMN: **JSON model + read-only SVG diagram** (no bpmn-js / external lib)
- 20.3 SMS: **logger stub** (writes `SMSDelivery` rows with `status='sent_stub'`)
- 20.4 Integration: **Connector registry + outbound webhook executor** with pre-seeded SAP/Oracle/Dynamics/NetSuite/Salesforce catalog rows (configurable, not live-wired)
- Ship all 5 sub-modules in one go
- Full pytest suite + idempotent seeder

---

## 0. Sub-module → model map (22 models total)

| # | Sub-module | Models |
|---|---|---|
| 20.1 | Visual Workflow Designer | `ProcessCategory`, `ProcessDefinition` (auto `BPM-00001`), `ProcessNode`, `ProcessTransition`, `ProcessInstance` (auto `PI-00001`), `ProcessVariable`, `ProcessActivity` |
| 20.2 | Approval Engine | `ApprovalPolicy`, `ApprovalLevel`, `ApprovalRequest` (auto `APR-00001`), `ApprovalDelegation`, `ApprovalActionLog`, `EscalationRule` |
| 20.3 | Notification & Escalation Matrix | `NotificationChannel`, `NotificationTemplate`, `NotificationRule` (auto `NR-00001`), `Notification` (auto `NTF-00001`), `NotificationDelivery`, `SMSDelivery` |
| 20.4 | Integration Orchestration | `Connector` (auto `CON-00001`), `ConnectorEndpoint`, `IntegrationFlow`, `FlowStep`, `IntegrationRun` (auto `IR-00001`), `WebhookOutboxEntry` |
| 20.5 | Process Mining & Optimization | `ProcessMetric`, `BottleneckAnalysis` (auto `BA-00001`), `ProcessOptimizationSuggestion` (auto `POS-00001`), `CycleTimeReport` |

(some models are shared between sub-modules; final count after dedup ≈ **22**.)

All inherit `TenantAwareModel, TimeStampedModel`. Auto-numbering via `services/numbering.next_code()` assigned in `save()` before `super().save()`. Decimal/integer fields get `MinValueValidator`/`MaxValueValidator` (L-02). Audit/log child FKs use `on_delete=PROTECT` (L-17); structural children use `CASCADE`.

### Key model fields (condensed)

#### 20.1 Visual Workflow Designer
- **ProcessCategory** — `name`, `code` (unique per tenant), `description`, `is_active`. `unique_together(tenant,code)`.
- **ProcessDefinition** — `code` (`BPM-00001`), `name`, `version` str default `1.0`, `category` FK SET_NULL, `description` text, `bpmn_model` JSON (canonical store: `{"nodes":[...], "edges":[...], "lanes":[...]}`), `status` (draft/active/archived), `owner` FK→User SET_NULL, `is_default` bool. `unique_together(tenant,code,version)`.
- **ProcessNode** — `definition` FK CASCADE, `node_key` str (matches JSON key), `node_type` (start/end/user_task/service_task/gateway_exclusive/gateway_parallel/timer/webhook), `name`, `lane` str, `position_x` int, `position_y` int, `config_json` JSON, `order` int. `unique_together(definition,node_key)`.
- **ProcessTransition** — `definition` FK CASCADE, `from_node` FK→ProcessNode PROTECT, `to_node` FK→ProcessNode PROTECT, `name`, `condition_expr` text (whitelist evaluator — re-uses the iot `_safe_eval` pattern; no `eval()`).
- **ProcessInstance** — `code` (`PI-00001`), `definition` FK PROTECT, `started_by` FK→User SET_NULL, `started_at` datetime auto, `completed_at` datetime null, `status` (pending/running/completed/cancelled/error), `current_node` FK→ProcessNode SET_NULL, `context_json` JSON (initial vars), `business_object_type` str (e.g. `procurement.PurchaseOrder`), `business_object_id` int null. Used to bind a runtime instance to any tenant business object.
- **ProcessVariable** — `instance` FK CASCADE, `name` str, `value_text` text, `value_type` (string/int/decimal/bool/date). `unique_together(instance,name)`.
- **ProcessActivity** — append-only execution log: `instance` FK PROTECT, `node` FK→ProcessNode SET_NULL, `event` (entered/completed/skipped/error/cancelled), `actor` FK→User SET_NULL, `recorded_at` datetime auto, `notes` text, `payload_json` JSON.

#### 20.2 Approval Engine
- **ApprovalPolicy** — `name`, `code`, `description`, `applies_to_type` str (model label like `procurement.PurchaseOrder`), `is_active` bool. `unique_together(tenant,code)`.
- **ApprovalLevel** — `policy` FK CASCADE, `level_no` int, `name`, `approver_role` (department_head/quality_manager/compliance_officer/plant_manager/cfo/cto/ceo/custom), `min_approvers` int default 1, `sla_hours` int (escalation threshold), `allow_delegation` bool default True. `unique_together(policy,level_no)`.
- **ApprovalRequest** — `code` (`APR-00001`), `policy` FK PROTECT, `current_level_no` int default 1, `subject` str, `business_object_type` str, `business_object_id` int null, `status` (pending/in_progress/approved/rejected/cancelled/escalated), `requested_by` FK→User SET_NULL, `requested_at` datetime auto, `decided_at` datetime null, `due_at` datetime (computed: requested_at + level.sla_hours), `notes` text.
- **ApprovalDelegation** — `delegator` FK→User PROTECT, `delegate` FK→User PROTECT, `policy` FK→ApprovalPolicy SET_NULL null (null = global delegation), `starts_at` date, `ends_at` date, `reason` text, `is_active` bool. `unique_together(tenant,delegator,policy,starts_at)`.
- **ApprovalActionLog** — append-only: `request` FK→ApprovalRequest PROTECT, `level_no` int, `decision` (approve/reject/delegate/escalate/recall), `actor` FK→User SET_NULL, `delegated_to` FK→User SET_NULL null, `decided_at` datetime auto, `notes` text.
- **EscalationRule** — `policy` FK CASCADE, `level_no` int, `trigger_hours_overdue` int, `escalate_to_role` str, `notify_channels` JSON (list of channel codes). `unique_together(policy,level_no,trigger_hours_overdue)`.

#### 20.3 Notification & Escalation Matrix
- **NotificationChannel** — `code` (email/sms/in_app/webhook), `name`, `is_active` bool, `config_json` JSON. `unique_together(tenant,code)`.
- **NotificationTemplate** — `code`, `name`, `event_type` str (e.g. `approval.requested`, `approval.escalated`, `process.completed`), `subject_template` str (Django template syntax), `body_template` text, `channels` JSON (list of channel codes), `is_active`. `unique_together(tenant,code)`.
- **NotificationRule** — `code` (`NR-00001`), `name`, `event_type` str (filter), `template` FK→NotificationTemplate PROTECT, `delay_minutes` int default 0, `is_active` bool. `unique_together(tenant,code)`.
- **Notification** — `code` (`NTF-00001`), `rule` FK→NotificationRule SET_NULL, `event_type` str, `recipient` FK→User PROTECT, `subject` str, `body` text, `status` (pending/sent/failed/skipped), `payload_json` JSON, `triggered_at` datetime auto, `dispatched_at` datetime null. `unique_together(tenant,code)`.
- **NotificationDelivery** — append-only per-channel: `notification` FK PROTECT, `channel` FK→NotificationChannel PROTECT, `status` (sent/failed/skipped), `external_ref` str, `attempted_at` datetime auto, `error_message` text.
- **SMSDelivery** — `to_phone` str, `body` str, `status` (sent_stub/failed), `notification` FK→Notification SET_NULL null, `sent_at` datetime auto. (stub-only; surfaces every SMS so QA can verify wiring without a Twilio account.)

#### 20.4 Integration Orchestration
- **Connector** — `code` (`CON-00001`), `name`, `connector_type` (rest_api/webhook/file_drop/db_pull/erp_sap/erp_oracle/erp_dynamics/erp_netsuite/crm_salesforce/crm_hubspot/other), `base_url` str, `auth_method` (none/basic/bearer/api_key/oauth2), `auth_secret_hash` str (stop-gap stable token — flag for KMS rotation in prod, like `iot.DeviceBroker.password_hash`), `is_active` bool. `unique_together(tenant,code)`.
- **ConnectorEndpoint** — `connector` FK CASCADE, `name`, `path` str, `method` (GET/POST/PUT/PATCH/DELETE), `headers_json` JSON, `request_template` text (Django-template body), `is_active`. `unique_together(connector,name)`.
- **IntegrationFlow** — `code`, `name`, `description`, `trigger_type` (manual/cron/event/webhook), `trigger_config` JSON, `is_active` bool. `unique_together(tenant,code)`.
- **FlowStep** — `flow` FK CASCADE, `step_no` int, `name`, `step_type` (http_call/transform/branch/log/sleep), `endpoint` FK→ConnectorEndpoint SET_NULL null, `config_json` JSON, `on_failure` (abort/continue/retry). `unique_together(flow,step_no)`.
- **IntegrationRun** — `code` (`IR-00001`), `flow` FK PROTECT, `status` (pending/running/completed/failed/cancelled), `triggered_by` FK→User SET_NULL, `started_at` datetime, `finished_at` datetime null, `error_message` text, `result_json` JSON.
- **WebhookOutboxEntry** — outbound webhook delivery row: `flow_run` FK→IntegrationRun SET_NULL null, `target_url` URLField, `payload_json` JSON, `status` (pending/sent/failed/retrying), `attempts` int default 0, `last_attempt_at` datetime null, `next_attempt_at` datetime null, `response_status` int null, `response_body` text.

#### 20.5 Process Mining & Optimization
- **ProcessMetric** — `instance` FK→ProcessInstance CASCADE, `metric_type` (cycle_time / wait_time / processing_time / handoff_count), `value_seconds` decimal, `recorded_at` datetime auto.
- **BottleneckAnalysis** — `code` (`BA-00001`), `definition` FK→ProcessDefinition PROTECT, `period_start` date, `period_end` date, `bottleneck_node` FK→ProcessNode SET_NULL, `avg_wait_seconds` decimal, `instance_count` int, `severity` (low/medium/high/critical), `notes` text.
- **ProcessOptimizationSuggestion** — `code` (`POS-00001`), `definition` FK PROTECT, `analysis` FK→BottleneckAnalysis SET_NULL, `suggestion_type` (reorder_steps/parallelize/auto_route/remove_step/add_validation), `description` text, `expected_savings_pct` decimal (`MinValueValidator(0)`, `MaxValueValidator(100)`), `status` (new/acknowledged/dismissed/applied), `acknowledged_by` FK→User SET_NULL null, `notes` text.
- **CycleTimeReport** — `code`, `definition` FK PROTECT, `period_start` date, `period_end` date, `instance_count` int, `avg_cycle_seconds` decimal, `p95_cycle_seconds` decimal, `min_cycle_seconds` decimal, `max_cycle_seconds` decimal. `unique_together(tenant,definition,period_start,period_end)`.

**Preflight (L-25):** before writing FKs/signals, inspect actual field shapes on `accounts.User` (role + tenant), `dms.DocumentApprovalRequest` (cross-link target), `iot._safe_eval` (reuse the same evaluator pattern), and `core.Tenant` to keep type signatures honest.

---

## 1. Cross-module signal hooks (apps/wfa/signals.py)

All handlers module-level, `dispatch_uid='wfa.<action>'`, L-23 best-effort logging.

| # | Trigger | Effect | Idempotency |
|---|---|---|---|
| 1 | `ProcessInstance.post_save(status changes)` | Append `ProcessActivity` row + audit log | dedup on `(instance, event, recorded_at)` |
| 2 | `ApprovalRequest.post_save(status='approved'/'rejected')` | Append `ApprovalActionLog` if not already + auto-trigger `NotificationRule(event_type='approval.completed')` | Skipped if log entry already exists for the transition |
| 3 | `Notification.post_save(status='pending')` | Dispatch fanout per `template.channels` via `services/notification.dispatch()` | Re-save with same status is no-op (already dispatched check) |
| 4 | `IntegrationRun.post_save(status='failed')` | Auto-create `Notification(event_type='integration.failed')` | Once per run |
| 5 | `ProcessInstance.post_save(status='completed')` | Recompute `ProcessMetric` rows for instance + flag `cycle_time` | One row per metric_type per instance |
| 6 | `dms.DocumentApprovalRequest.post_save(status='approved')` (cross-module) | Auto-complete any linked `wfa.ApprovalRequest(business_object_type='dms.DocumentApprovalRequest', business_object_id=<pk>)` | Conditional UPDATE; idempotent |
| 7 | `procurement.PurchaseOrder.post_save(status='submitted')` (cross-module) | When an active `ApprovalPolicy(applies_to_type='procurement.PurchaseOrder')` exists, auto-create `ApprovalRequest` | One open request per (PO, policy) |
| 8 | `ApprovalRequest.post_save(status='escalated')` | Auto-create `Notification(event_type='approval.escalated')` for `escalate_to_role` users | Once per request per level_no |

**Cross-module enforcement.** Hook #7 is implemented as a *soft, opt-in* hook — only fires when an active policy exists. No-op when no policy is configured (zero behavior change to existing modules).

**Audit factory.** A `_make_audit_handler(model_label)` factory mirrors the pattern from `eam`/`labor`/`cost` — registers `pre_save`+`post_save` for 8 status-tracked models (ProcessDefinition / ProcessInstance / ApprovalPolicy / ApprovalRequest / NotificationRule / Connector / IntegrationFlow / IntegrationRun). L-18 `weak=False`. Best-effort logging on audit-write failure (L-23).

---

## 2. Services (pure / single-writer)

- [`services/numbering.py`](apps/wfa/services/numbering.py) — atomic auto-code (copy pattern from dms/rma).
- [`services/bpmn_engine.py`](apps/wfa/services/bpmn_engine.py) — `start_instance(definition, business_object)`, `advance_instance(instance, action)`, `evaluate_transition(transition, vars)` with whitelist `_safe_eval` (mirror `iot/services/twin.py` pattern — no `eval()`, no `exec()`).
- [`services/approval.py`](apps/wfa/services/approval.py) — `submit_request`, `approve`, `reject`, `delegate`, `escalate`, `recall`; all use race-safe conditional `UPDATE ... WHERE status=...` and write append-only `ApprovalActionLog` rows.
- [`services/notification.py`](apps/wfa/services/notification.py) — `render_template(template, context)`, `dispatch(notification)` fanning to email (Django `send_mail`), SMS (stub `SMSDelivery` insert), in-app (write-through to notification row), webhook (`WebhookOutboxEntry` insert).
- [`services/integration.py`](apps/wfa/services/integration.py) — `execute_flow(flow, context)`, `execute_step(step, context)` — pure HTTP via `requests` library; never imports models at module level.
- [`services/process_mining.py`](apps/wfa/services/process_mining.py) — `compute_cycle_time(instance)`, `detect_bottlenecks(definition, period)`, `generate_suggestions(analysis)`.

---

## 3. Phase A — Scaffold, models, migration

- [ ] `apps/wfa/__init__.py`, `apps.py` (`WfaConfig`, `verbose_name='Workflow & Business Process Automation'`, `ready()` imports signals), `migrations/__init__.py`
- [ ] `apps/wfa/services/__init__.py` + the 6 service modules above (numbering/bpmn_engine/approval/notification/integration/process_mining)
- [ ] `apps/wfa/models.py` — all 22 models
- [ ] `apps/wfa/admin.py` — `@admin.register` per model with `tenant` in list_display + autocomplete FKs; **`ApprovalActionLogAdmin.readonly_fields = '__all__'`** + **`ProcessActivityAdmin.readonly_fields = '__all__'`** + **`NotificationDeliveryAdmin.readonly_fields = '__all__'`** + **`WebhookOutboxEntryAdmin.readonly_fields = '__all__'`** (immutable append-only ledgers)
- [ ] Register `'apps.wfa'` in `config/settings.py` INSTALLED_APPS (end of Local block)
- [ ] Mount `path('wfa/', include('apps.wfa.urls'))` in `config/urls.py`
- [ ] `python manage.py makemigrations wfa` → `0001_initial.py`; `python manage.py migrate`

## 4. Phase B — Forms, views, URLs

- [ ] `apps/wfa/forms.py` — ~22 ModelForms with `tenant=` kwarg, per-tenant FK querysets, explicit `clean()` for `unique_together` (L-01), decimal validators (L-02), per-workflow forms (L-14): `ApprovalRejectForm` (notes required), `ApprovalDelegationForm` (delegate required), `ProcessInstanceCancelForm` (reason required), `OptimizationDismissForm` (notes required); BPMN editor uses `ProcessNodeForm` + `ProcessTransitionForm` inline; `IntegrationFlowForm` validates JSON shape.
- [ ] `apps/wfa/views.py` — `PAGE_SIZE=25`; `@login_required` everywhere; `request.tenant` filter first; list (search+filters+pagination, passes `*_choices`/FK querysets per **Filter Rules**), create, detail, edit, delete (POST-only, status-gated to match templates — L-03); dashboard `index` with KPI cards (active processes, running instances, pending approvals, my pending, sent notifications today, failed integrations, optimization suggestions); BPMN diagram view renders a server-side SVG (Python builder; no JS canvas).
- [ ] `apps/wfa/urls.py` — `app_name='wfa'`; standard `*_list/_create/_detail/_edit/_delete` + workflow actions per sub-module (start_instance, advance_instance, cancel_instance, submit_approval, approve, reject, delegate, escalate, dispatch_notification, retry_integration, acknowledge_suggestion)
- [ ] State-mutating views (approve / reject / delegate / cancel / archive / connector secret-edit) guarded by tenant-admin check (L-10); notification dispatch is callable by any logged-in user for their own notifications.

## 5. Phase C — Signals

- [ ] `apps/wfa/signals.py` — implement the 8 hooks + audit factory above; L-18 `weak=False` for module-level handlers; L-23 best-effort `logger.warning(..., exc_info=True)` on every audit-write try/except.

## 6. Phase D — Templates + sidebar

- [ ] `templates/wfa/index.html` (dashboard)
- [ ] `templates/wfa/_pagination.html` (shared)
- [ ] processes/ (4 templates: list / form / detail / diagram)
- [ ] processes/nodes/ (form), processes/transitions/ (form)
- [ ] instances/ (4 templates: list / form / detail / start)
- [ ] approvals/policies/ (3) + levels/ (form) + escalation_rules/ (form) + requests/ (3) + decisions/ (form) + delegations/ (2)
- [ ] notifications/channels/ (2) + templates/ (2) + rules/ (2) + list + detail + deliveries/ + sms/ (read-only stub log)
- [ ] integrations/connectors/ (3) + endpoints/ (form) + flows/ (3) + steps/ (form) + runs/ (2) + webhook_outbox/ (read-only)
- [ ] mining/bottlenecks/ (2) + suggestions/ (2) + cycle_time/ (2)
- [ ] **Sidebar** — add a new collapsible group "Workflow & Automation" guarded by `{% if request.user.role != 'supplier' and request.user.role != 'customer' %}` after the Documents & KMS group at templates/partials/sidebar.html:459 with links: Dashboard / Processes / Instances / Approval Policies / Approval Requests / My Approvals / Notification Rules / Connectors / Flows / Optimization Suggestions

## 7. Phase E — Management commands + seed_data wiring

- [ ] `apps/wfa/management/__init__.py` + `commands/__init__.py`
- [ ] `apps/wfa/management/commands/seed_wfa.py` — idempotent demo seeder per tenant: 3 `ProcessCategory` + 2 `ProcessDefinition` (PO Approval Flow + RMA Triage Flow) with ~6 nodes + 6 transitions each, 1 running `ProcessInstance` per definition with sample activity log, 2 `ApprovalPolicy` (PO + RMA) with 3 levels each + 1 escalation rule, 3 `ApprovalRequest` rows across statuses (pending/approved/rejected), 1 `ApprovalDelegation`, 3 `NotificationChannel` (email/sms/in_app), 4 `NotificationTemplate` (approval requested/approved/rejected/escalated), 4 `NotificationRule`, 8 `Notification` rows + matching `NotificationDelivery`, 6 `Connector` catalog rows (SAP/Oracle/Dynamics/NetSuite/Salesforce/HubSpot, all `is_active=False` for safety), 2 `IntegrationFlow` (PO sync + Customer sync) with 3 steps each, 1 completed `IntegrationRun`, 5 `ProcessMetric` rows, 1 `BottleneckAnalysis`, 2 `ProcessOptimizationSuggestion`, 1 `CycleTimeReport`.
- [ ] `apps/wfa/management/commands/run_notifications.py` — cron sweeper: pick up `Notification(status='pending')` rows + dispatch via `services/notification.dispatch()`; `--dry-run` + `--tenant <slug>` flags.
- [ ] `apps/wfa/management/commands/escalate_approvals.py` — cron sweeper: pick up `ApprovalRequest(status='pending', due_at < now())` + escalate per `EscalationRule`; race-safe conditional UPDATE.
- [ ] `apps/wfa/management/commands/mine_processes.py` — refresh `ProcessMetric` rows + regenerate `BottleneckAnalysis` for active definitions.
- [ ] Edit `apps/core/management/commands/seed_data.py` to call `seed_wfa` at the end (wrapped in try/except like the recent additions).

## 8. Phase F — pytest suite (~100 tests)

- [ ] `apps/wfa/tests/__init__.py` + `conftest.py` (tenant + user + business-object fixtures)
- [ ] `test_models.py` — auto-numbering (BPM/PI/APR/NR/NTF/CON/IR/BA/POS), computed fields (`ApprovalRequest.due_at`, `ProcessMetric.value_seconds`), L-02 validators, JSON field shape
- [ ] `test_forms.py` — L-01 unique_together `clean()` on every tenant catalog, L-14 per-workflow required (reject notes / delegation target / cancel reason / dismiss notes), JSON validation
- [ ] `test_services.py` — `bpmn_engine.advance_instance` happy path + `_safe_eval` rejects `__import__` / `eval` / attribute access, `approval.escalate` SLA math, `notification.dispatch` email + SMS stub + in_app fanout, `integration.execute_flow` happy + failure path, `process_mining.compute_cycle_time` arithmetic
- [ ] `test_signals.py` — all 8 cross-module hooks + idempotency on re-save, L-18 dispatch_uid presence guard
- [ ] `test_views.py` — full HTTP CRUD smoke + workflow walks (approve/reject/delegate/escalate, integration run, instance start/cancel)
- [ ] `test_security.py` — multi-tenant IDOR (cross-tenant 404 on every detail URL), RBAC matrix (staff blocked from policy/rule/connector mutations — L-10), anonymous-redirect on all list URLs, broker secret NOT exposed in connector list
- [ ] `test_seeder.py` — `seed_wfa` idempotency + `--flush` consistency + `run_notifications --dry-run` safety + `escalate_approvals --dry-run` safety

## 9. Phase G — README updates (MANDATORY per CLAUDE.md)

- [ ] **Highlights** — add Module 20 bullet matching the verbose style used for Module 19
- [ ] **TOC** — add `Module 20 — Workflow & Business Process Automation` link
- [ ] **Module 1-19 → Module 1-20** in the intro paragraph
- [ ] **Screenshots / UI Tour** — add ~25 `/wfa/...` route rows under the DMS section
- [ ] **Project Structure** — add the `apps/wfa/` tree under `apps/dms/` and the `templates/wfa/` line under `templates/dms/`
- [ ] **Module 20 dedicated section** — Sub-module overview tables, model lists, service references, signal hook table, route table, RBAC notes, test suite mention, out-of-scope list (BPMN drag-and-drop canvas, real ERP connectors, Twilio SMS)
- [ ] **Management Commands** — `seed_wfa`, `run_notifications`, `escalate_approvals`, `mine_processes`, `pytest apps/wfa/tests/` rows
- [ ] **Seeded Demo Data** — add Module 20 bullet describing the seeded fixture set
- [ ] **Roadmap** — strike through `20. Workflow & Business Process Automation` and append ✅ shipped
- [ ] **Phase 1 intro text** — bump "Modules 1-19" → "Modules 1-20"
- [ ] **seed_data orchestrator** mention — extend the existing seed_data row to include `seed_wfa`

## 10. Phase H — Per-file PowerShell git commit snippets

Per project rules: **one `git add` + one `git commit` per file, every time** — even `__init__.py` files. Output as a PowerShell-safe block separating commands with `;` (never `&&`). Final block will be ~80–120 commits.

Order: scaffold → models → migration → admin → settings → urls → services → forms → views → urls.py → signals → templates (alphabetical) → sidebar → seeders → tests → README → seed_data orchestrator.

---

## Out-of-scope (deferred / explicit in README)
- **bpmn-js drag-and-drop canvas** — JSON model + read-only SVG only in v1.
- **Twilio (or any real SMS gateway)** — stub-only `SMSDelivery` ledger.
- **Live ERP integrations** — connector catalog only; rows exist for SAP/Oracle/Dynamics/NetSuite/Salesforce/HubSpot but ship inactive. Webhook outbox is wired and works end-to-end.
- **Process Mining ML** — heuristic averages + bottleneck detection only; no scikit-learn / numpy dependency.
- **Visual rule editor** for `EscalationRule` — admin form only.
- **OAuth2 flow** for connectors — only auth metadata stored; runtime token refresh deferred.

---

## Risks + how I'll mitigate them
1. **Migration size** — 22 models in one migration. Mitigation: makemigrations run inside a fresh shell; if errors, split into 0001 + 0002.
2. **JSON parsing perf in admin** — `bpmn_model` could be large. Mitigation: admin uses textarea (not custom widget); list_display doesn't expand JSON.
3. **Cross-module signal load** — hooks #6 + #7 add overhead to every dms/procurement save. Mitigation: gate every cross-module hook on `Model.objects.filter(applies_to_type=..., is_active=True).exists()` short-circuit before doing work.
4. **`_safe_eval` security** — copy the iot pattern verbatim (whitelist parser only — `+ - * / ()`, `min/max/abs`, var refs, decimal literals). Test cases include `__import__` / `eval` / `lambda` / attribute access / `**` operator rejection.
5. **PowerShell commit snippet length** — accepted per project rules; will hand back in one block.

---

## Definition of done
- All migrations apply cleanly.
- `python manage.py seed_data --flush` runs end-to-end without errors and creates demo data in each of the 3 tenants.
- All pytest files pass (`pytest apps/wfa/tests/`).
- Dashboard renders for `admin_acme` showing populated KPI cards.
- Every list page accepts filter params and round-trips correctly.
- README updates committed in the same set as code.
- Per-file PowerShell commit snippets handed back at the end.
