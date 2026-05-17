"""Idempotent seeder for Module 20 - Workflow & Business Process Automation."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Tenant, set_current_tenant
from apps.wfa import models as M


PROCESS_FIXTURES = [
    {
        'code': 'PO-APPROVAL',
        'name': 'Purchase Order Approval',
        'description': 'Standard PO approval flow with department-head sign-off.',
        'nodes': [
            ('start', 'start', 'Start'),
            ('validate', 'user_task', 'Validate PO'),
            ('gateway', 'gateway_exclusive', 'Amount Gateway'),
            ('approve_dept', 'user_task', 'Dept Head Approval'),
            ('approve_cfo', 'user_task', 'CFO Approval'),
            ('end', 'end', 'End'),
        ],
        'transitions': [
            ('start', 'validate', '', ''),
            ('validate', 'gateway', 'after validation', ''),
            ('gateway', 'approve_dept', 'small PO', 'amount < 10000'),
            ('gateway', 'approve_cfo', 'large PO', 'amount >= 10000'),
            ('approve_dept', 'end', '', ''),
            ('approve_cfo', 'end', '', ''),
        ],
    },
    {
        'code': 'RMA-TRIAGE',
        'name': 'RMA Request Triage',
        'description': 'Triage and route an inbound RMA request.',
        'nodes': [
            ('start', 'start', 'Receive'),
            ('triage', 'user_task', 'Triage'),
            ('investigate', 'service_task', 'Investigate'),
            ('decide', 'gateway_exclusive', 'Decision'),
            ('approve', 'user_task', 'Approve'),
            ('reject', 'user_task', 'Reject'),
            ('end', 'end', 'End'),
        ],
        'transitions': [
            ('start', 'triage', '', ''),
            ('triage', 'investigate', '', ''),
            ('investigate', 'decide', '', ''),
            ('decide', 'approve', 'approve path', "decision == 'approve'"),
            ('decide', 'reject', 'reject path', "decision == 'reject'"),
            ('approve', 'end', '', ''),
            ('reject', 'end', '', ''),
        ],
    },
]

NOTIFICATION_TEMPLATES = [
    {
        'code': 'APR-REQUESTED', 'name': 'Approval Requested',
        'event_type': 'approval.requested',
        'subject_template': 'New approval request {{ request_code }}',
        'body_template': 'You have a new approval request for {{ subject }} ({{ policy }}). Please review.',
        'channels': ['email', 'in_app'],
    },
    {
        'code': 'APR-APPROVED', 'name': 'Approval Approved',
        'event_type': 'approval.approved',
        'subject_template': 'Your request {{ request_code }} has been approved',
        'body_template': '{{ subject }} was approved by your reviewer.',
        'channels': ['email', 'in_app'],
    },
    {
        'code': 'APR-REJECTED', 'name': 'Approval Rejected',
        'event_type': 'approval.rejected',
        'subject_template': 'Your request {{ request_code }} was rejected',
        'body_template': '{{ subject }} was rejected. Please see the action log for details.',
        'channels': ['email', 'in_app', 'sms'],
    },
    {
        'code': 'APR-ESCALATED', 'name': 'Approval Escalated',
        'event_type': 'approval.escalated',
        'subject_template': 'Approval {{ request_code }} has been escalated',
        'body_template': 'The request {{ subject }} has been escalated due to SLA breach.',
        'channels': ['email', 'in_app'],
    },
    {
        'code': 'INT-FAILED', 'name': 'Integration Failed',
        'event_type': 'integration.failed',
        'subject_template': 'Integration run {{ run_code }} failed',
        'body_template': 'Flow {{ flow }} failed: {{ error }}',
        'channels': ['email', 'in_app'],
    },
]

CONNECTOR_FIXTURES = [
    ('SAP-ERP', 'SAP ERP', 'erp_sap', 'https://erp.example.com/sap', 'oauth2'),
    ('ORACLE-ERP', 'Oracle ERP', 'erp_oracle', 'https://erp.example.com/oracle', 'bearer'),
    ('DYNAMICS-ERP', 'Microsoft Dynamics 365', 'erp_dynamics', 'https://erp.example.com/dynamics', 'oauth2'),
    ('NETSUITE-ERP', 'NetSuite', 'erp_netsuite', 'https://erp.example.com/netsuite', 'bearer'),
    ('SALESFORCE-CRM', 'Salesforce CRM', 'crm_salesforce', 'https://crm.example.com/salesforce', 'oauth2'),
    ('HUBSPOT-CRM', 'HubSpot CRM', 'crm_hubspot', 'https://crm.example.com/hubspot', 'api_key'),
]


class Command(BaseCommand):
    help = 'Seed Module 20 (Workflow & Business Process Automation) demo data per tenant.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Wipe existing WFA data per tenant before seeding')
        parser.add_argument('--tenant', help='Slug of a single tenant to seed (default: all)')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if options.get('tenant'):
            tenants = tenants.filter(slug=options['tenant'])
        if not tenants.exists():
            self.stdout.write(self.style.WARNING('No active tenants found.'))
            return
        for tenant in tenants:
            self._seed_tenant(tenant, flush=options.get('flush', False))
        self.stdout.write(self.style.SUCCESS(
            'Done. Log in as a tenant admin (admin_<slug>) to see the data. '
            "The superuser 'admin' has no tenant - data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant, flush=False):
        set_current_tenant(tenant)
        self.stdout.write(self.style.HTTP_INFO(f'-> {tenant.slug}'))
        if flush:
            self._flush(tenant)
        if M.ProcessDefinition.all_objects.filter(tenant=tenant).exists() and not flush:
            self.stdout.write(self.style.WARNING(f'   data already exists, skipping (use --flush to reseed)'))
            return
        with transaction.atomic():
            self._seed_processes(tenant)
            self._seed_approvals(tenant)
            self._seed_notifications(tenant)
            self._seed_integrations(tenant)
            self._seed_mining(tenant)
        self.stdout.write(self.style.SUCCESS(f'   {tenant.slug} seeded'))

    def _flush(self, tenant):
        for model in (
            M.WebhookOutboxEntry, M.IntegrationRun, M.FlowStep, M.IntegrationFlow,
            M.ConnectorEndpoint, M.Connector,
            M.NotificationDelivery, M.SMSDelivery, M.Notification, M.NotificationRule,
            M.NotificationTemplate, M.NotificationChannel,
            M.ApprovalActionLog, M.ApprovalDelegation, M.ApprovalRequest,
            M.EscalationRule, M.ApprovalLevel, M.ApprovalPolicy,
            M.ProcessOptimizationSuggestion, M.BottleneckAnalysis, M.CycleTimeReport,
            M.ProcessMetric, M.ProcessActivity, M.ProcessVariable,
            M.ProcessInstance, M.ProcessTransition, M.ProcessNode,
            M.ProcessDefinition, M.ProcessCategory,
        ):
            model.all_objects.filter(tenant=tenant).delete()

    def _seed_processes(self, tenant):
        cats = {
            'OPS': M.ProcessCategory.all_objects.create(tenant=tenant, code='OPS', name='Operations'),
            'FIN': M.ProcessCategory.all_objects.create(tenant=tenant, code='FIN', name='Finance'),
            'SVC': M.ProcessCategory.all_objects.create(tenant=tenant, code='SVC', name='Service'),
        }
        for fixture in PROCESS_FIXTURES:
            cat = cats['FIN'] if fixture['code'] == 'PO-APPROVAL' else cats['SVC']
            d = M.ProcessDefinition.all_objects.create(
                tenant=tenant, code=fixture['code'], name=fixture['name'],
                category=cat, description=fixture['description'],
                status='active', is_default=fixture['code'] == 'PO-APPROVAL',
            )
            node_map = {}
            for idx, (key, ntype, name) in enumerate(fixture['nodes']):
                n = M.ProcessNode.all_objects.create(
                    tenant=tenant, definition=d, node_key=key, node_type=ntype,
                    name=name, position_x=40 + idx * 180, position_y=60,
                    order=idx,
                )
                node_map[key] = n
            for from_key, to_key, name, cond in fixture['transitions']:
                M.ProcessTransition.all_objects.create(
                    tenant=tenant, definition=d,
                    from_node=node_map[from_key],
                    to_node=node_map[to_key],
                    name=name,
                    condition_expr=cond,
                )
            # 1 running instance per definition
            start = node_map['start']
            instance = M.ProcessInstance.all_objects.create(
                tenant=tenant, definition=d,
                status='running', current_node=node_map.get('validate' if d.code == 'PO-APPROVAL' else 'triage'),
                context_json={'amount': 5000} if d.code == 'PO-APPROVAL' else {'decision': 'approve'},
                business_object_type='procurement.PurchaseOrder' if d.code == 'PO-APPROVAL' else 'rma.RMARequest',
                business_object_id=1,
            )
            M.ProcessActivity.all_objects.create(
                tenant=tenant, instance=instance, node=start, event='entered',
            )
            M.ProcessActivity.all_objects.create(
                tenant=tenant, instance=instance, node=instance.current_node,
                event='entered', recorded_at=timezone.now() + timedelta(seconds=5),
            )

    def _seed_approvals(self, tenant):
        po_policy = M.ApprovalPolicy.all_objects.create(
            tenant=tenant, code='POL-PO', name='Purchase Order Approval Policy',
            description='Two-level review for purchase orders.',
            applies_to_type='procurement.PurchaseOrder',
            is_active=True,
        )
        M.ApprovalLevel.all_objects.create(
            tenant=tenant, policy=po_policy, level_no=1, name='Dept Head Review',
            approver_role='department_head', min_approvers=1, sla_hours=24,
        )
        M.ApprovalLevel.all_objects.create(
            tenant=tenant, policy=po_policy, level_no=2, name='Plant Manager Review',
            approver_role='plant_manager', min_approvers=1, sla_hours=48,
        )
        M.EscalationRule.all_objects.create(
            tenant=tenant, policy=po_policy, level_no=1,
            trigger_hours_overdue=24, escalate_to_role='plant_manager',
            notify_channels=['email', 'in_app'],
        )
        rma_policy = M.ApprovalPolicy.all_objects.create(
            tenant=tenant, code='POL-RMA', name='RMA Approval Policy',
            description='Single-level Quality Manager review for RMA requests.',
            applies_to_type='rma.RMARequest', is_active=True,
        )
        M.ApprovalLevel.all_objects.create(
            tenant=tenant, policy=rma_policy, level_no=1, name='Quality Review',
            approver_role='quality_manager', min_approvers=1, sla_hours=48,
        )
        # Three sample requests
        requesters = list(tenant.user_set.filter(is_active=True)[:2]) if hasattr(tenant, 'user_set') else []
        if not requesters:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            requesters = list(User.objects.filter(tenant=tenant)[:2])
        for idx, (subj, status) in enumerate([
            ('PO PUR-00100 requires approval', 'in_progress'),
            ('PO PUR-00099 requires approval', 'approved'),
            ('PO PUR-00098 requires approval', 'rejected'),
        ]):
            req = M.ApprovalRequest.all_objects.create(
                tenant=tenant, policy=po_policy,
                subject=subj, business_object_type='procurement.PurchaseOrder',
                business_object_id=100 - idx,
                status=status,
                requested_by=requesters[0] if requesters else None,
                requested_at=timezone.now() - timedelta(days=idx + 1),
                decided_at=timezone.now() - timedelta(hours=12) if status in ('approved', 'rejected') else None,
                due_at=timezone.now() + timedelta(hours=24) if status == 'in_progress' else None,
            )
            M.ApprovalActionLog.all_objects.create(
                tenant=tenant, request=req, level_no=1,
                decision='submit', actor=requesters[0] if requesters else None,
            )
            if status == 'approved':
                M.ApprovalActionLog.all_objects.create(
                    tenant=tenant, request=req, level_no=1,
                    decision='approve', actor=requesters[0] if requesters else None,
                )
            elif status == 'rejected':
                M.ApprovalActionLog.all_objects.create(
                    tenant=tenant, request=req, level_no=1,
                    decision='reject', actor=requesters[0] if requesters else None,
                    notes='Budget exceeded',
                )
        if len(requesters) >= 2:
            M.ApprovalDelegation.all_objects.create(
                tenant=tenant, delegator=requesters[0], delegate=requesters[1],
                policy=None, starts_at=timezone.localdate(),
                ends_at=timezone.localdate() + timedelta(days=14),
                reason='Annual leave',
                is_active=True,
            )

    def _seed_notifications(self, tenant):
        channels = {}
        for code, name in [('email', 'Email'), ('sms', 'SMS (stub)'), ('in_app', 'In-App'), ('webhook', 'Webhook')]:
            channels[code] = M.NotificationChannel.all_objects.create(
                tenant=tenant, code=code, name=name, is_active=True,
            )
        templates = {}
        for fx in NOTIFICATION_TEMPLATES:
            templates[fx['event_type']] = M.NotificationTemplate.all_objects.create(
                tenant=tenant, code=fx['code'], name=fx['name'],
                event_type=fx['event_type'],
                subject_template=fx['subject_template'],
                body_template=fx['body_template'],
                channels=fx['channels'],
                is_active=True,
            )
        for event, name in [
            ('approval.requested', 'Approval Requested Rule'),
            ('approval.approved', 'Approval Approved Rule'),
            ('approval.rejected', 'Approval Rejected Rule'),
            ('approval.escalated', 'Approval Escalated Rule'),
            ('integration.failed', 'Integration Failure Rule'),
        ]:
            M.NotificationRule.all_objects.create(
                tenant=tenant, name=name, event_type=event,
                template=templates[event], delay_minutes=0, is_active=True,
            )

    def _seed_integrations(self, tenant):
        connectors = {}
        for code, name, ctype, base, auth in CONNECTOR_FIXTURES:
            connectors[code] = M.Connector.all_objects.create(
                tenant=tenant, code=code, name=name, connector_type=ctype,
                base_url=base, auth_method=auth, auth_secret_hash='',
                is_active=False,  # demo connectors stay inactive by default
                description='Pre-seeded demo connector. Configure credentials to enable.',
            )
        # 2 sample flows
        po_flow = M.IntegrationFlow.all_objects.create(
            tenant=tenant, code='FLOW-PO-SYNC', name='PO Sync to ERP',
            description='Push approved POs to the configured ERP connector.',
            trigger_type='event', trigger_config={'event': 'procurement.po.approved'},
            is_active=True,
        )
        for idx, (name, stype, oncfg) in enumerate([
            ('Log', 'log', 'continue'),
            ('Push to ERP', 'http_call', 'abort'),
            ('Log Outcome', 'log', 'continue'),
        ]):
            M.FlowStep.all_objects.create(
                tenant=tenant, flow=po_flow, step_no=idx + 1, name=name,
                step_type=stype, on_failure=oncfg,
            )
        cust_flow = M.IntegrationFlow.all_objects.create(
            tenant=tenant, code='FLOW-CUST-SYNC', name='Customer Sync from CRM',
            description='Pull customer master from CRM connector.',
            trigger_type='cron', trigger_config={'cron': '0 */6 * * *'},
            is_active=True,
        )
        for idx, (name, stype, oncfg) in enumerate([
            ('Fetch Customers', 'http_call', 'abort'),
            ('Transform', 'transform', 'continue'),
            ('Log', 'log', 'continue'),
        ]):
            M.FlowStep.all_objects.create(
                tenant=tenant, flow=cust_flow, step_no=idx + 1, name=name,
                step_type=stype, on_failure=oncfg,
            )
        # 1 completed run
        M.IntegrationRun.all_objects.create(
            tenant=tenant, flow=cust_flow, status='completed',
            started_at=timezone.now() - timedelta(hours=6),
            finished_at=timezone.now() - timedelta(hours=6, minutes=-2),
            result_json={'rows': 42},
        )

    def _seed_mining(self, tenant):
        definition = M.ProcessDefinition.all_objects.filter(tenant=tenant).first()
        if definition is None:
            return
        # 5 metric rows over the active instance
        instance = M.ProcessInstance.all_objects.filter(tenant=tenant, definition=definition).first()
        if instance is None:
            return
        for mt, secs in [('cycle_time', 1800), ('wait_time', 600), ('processing_time', 1200), ('handoff_count', 2)]:
            M.ProcessMetric.all_objects.create(
                tenant=tenant, instance=instance, metric_type=mt,
                value_seconds=Decimal(str(secs)),
            )
        ba = M.BottleneckAnalysis.all_objects.create(
            tenant=tenant, definition=definition,
            period_start=timezone.localdate() - timedelta(days=30),
            period_end=timezone.localdate(),
            bottleneck_node=definition.nodes.filter(node_type='user_task').first(),
            avg_wait_seconds=Decimal('3600'),
            instance_count=12,
            severity='medium',
            notes='Sample analysis from seeder.',
        )
        M.ProcessOptimizationSuggestion.all_objects.create(
            tenant=tenant, definition=definition, analysis=ba,
            suggestion_type='parallelize',
            description='Parallelize the Validate and Triage steps to cut hand-off time.',
            expected_savings_pct=Decimal('15'),
            status='new',
        )
        M.ProcessOptimizationSuggestion.all_objects.create(
            tenant=tenant, definition=definition, analysis=ba,
            suggestion_type='auto_route',
            description='Auto-route POs under $1000 directly to dept head.',
            expected_savings_pct=Decimal('22'),
            status='acknowledged',
        )
        M.CycleTimeReport.all_objects.create(
            tenant=tenant, definition=definition,
            period_start=timezone.localdate() - timedelta(days=30),
            period_end=timezone.localdate(),
            instance_count=12,
            avg_cycle_seconds=Decimal('7200'),
            p95_cycle_seconds=Decimal('14400'),
            min_cycle_seconds=Decimal('1800'),
            max_cycle_seconds=Decimal('28800'),
        )
