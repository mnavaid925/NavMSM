"""Module 20 - Workflow & Business Process Automation.

Sub-modules:
    20.1  Visual Workflow Designer
            (ProcessCategory, ProcessDefinition, ProcessNode,
             ProcessTransition, ProcessInstance, ProcessVariable,
             ProcessActivity)
    20.2  Approval Engine
            (ApprovalPolicy, ApprovalLevel, ApprovalRequest,
             ApprovalDelegation, ApprovalActionLog, EscalationRule)
    20.3  Notification & Escalation Matrix
            (NotificationChannel, NotificationTemplate, NotificationRule,
             Notification, NotificationDelivery, SMSDelivery)
    20.4  Integration Orchestration
            (Connector, ConnectorEndpoint, IntegrationFlow, FlowStep,
             IntegrationRun, WebhookOutboxEntry)
    20.5  Process Mining & Optimization
            (ProcessMetric, BottleneckAnalysis,
             ProcessOptimizationSuggestion, CycleTimeReport)

Cross-module integration (see apps/wfa/signals.py):
    - ProcessInstance status change -> append ProcessActivity log
    - ApprovalRequest approved/rejected -> log + notification fanout
    - Notification status='pending' -> dispatch to channels
    - IntegrationRun failed -> auto-notification
    - dms.DocumentApprovalRequest approved -> close linked wfa.ApprovalRequest
    - procurement.PurchaseOrder submitted -> auto-create ApprovalRequest
      when an active policy matches

Lessons applied:
    * L-01 unique_together with tenant excluded -> form-level clean()
    * L-02 every Decimal / IntegerField carries explicit validators
    * L-03 view+template status gate parity via is_*() helpers
    * L-12 auto-numbering via services/numbering.next_code()
    * L-13 transaction.atomic() around denorm bumps (signals)
    * L-14 per-workflow forms enforce required fields at transition
    * L-17 PROTECT on audit-trail children (ApprovalActionLog.request,
            ProcessActivity.instance, NotificationDelivery.notification,
            WebhookOutboxEntry.flow_run)
    * L-18 weak=False + dispatch_uid on every signal handler
    * L-21 time-driven escalation via escalate_approvals cron
    * L-22 (no file uploads in this module)
    * L-23 audit emit failures logged at WARNING, never raise
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel
from apps.wfa.services.numbering import next_code


# ============================================================================
# 20.1  VISUAL WORKFLOW DESIGNER
# ============================================================================

class ProcessCategory(TenantAwareModel, TimeStampedModel):
    """Top-level taxonomy for process definitions (Sales / Operations / HR)."""

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')
        verbose_name_plural = 'Process categories'

    def __str__(self):
        return self.name


PROCESS_STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('active', 'Active'),
    ('archived', 'Archived'),
]


class ProcessDefinition(TenantAwareModel, TimeStampedModel):
    """A versioned BPMN process. The canonical model is the bpmn_model
    JSON blob; ProcessNode + ProcessTransition rows mirror it for
    indexed querying.
    """

    code = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=20, default='1.0')
    category = models.ForeignKey(
        ProcessCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='definitions',
    )
    description = models.TextField(blank=True)
    bpmn_model = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=PROCESS_STATUS_CHOICES, default='draft')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wfa_owned_processes',
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'code', 'version')

    def __str__(self):
        return f'{self.code} {self.name} v{self.version}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(ProcessDefinition, self.tenant, 'BPM')
        super().save(*args, **kwargs)

    def is_editable(self):
        return self.status == 'draft'


NODE_TYPE_CHOICES = [
    ('start', 'Start'),
    ('end', 'End'),
    ('user_task', 'User Task'),
    ('service_task', 'Service Task'),
    ('gateway_exclusive', 'Exclusive Gateway'),
    ('gateway_parallel', 'Parallel Gateway'),
    ('timer', 'Timer Event'),
    ('webhook', 'Webhook Event'),
]


class ProcessNode(TenantAwareModel, TimeStampedModel):
    definition = models.ForeignKey(
        ProcessDefinition, on_delete=models.CASCADE, related_name='nodes',
    )
    node_key = models.CharField(max_length=80)
    node_type = models.CharField(max_length=24, choices=NODE_TYPE_CHOICES)
    name = models.CharField(max_length=200)
    lane = models.CharField(max_length=80, blank=True)
    position_x = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(5000)])
    position_y = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(5000)])
    config_json = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['definition', 'order']
        unique_together = ('definition', 'node_key')

    def __str__(self):
        return f'{self.definition.code}:{self.node_key}'


class ProcessTransition(TenantAwareModel, TimeStampedModel):
    definition = models.ForeignKey(
        ProcessDefinition, on_delete=models.CASCADE, related_name='transitions',
    )
    from_node = models.ForeignKey(
        ProcessNode, on_delete=models.PROTECT, related_name='outgoing',
    )
    to_node = models.ForeignKey(
        ProcessNode, on_delete=models.PROTECT, related_name='incoming',
    )
    name = models.CharField(max_length=120, blank=True)
    condition_expr = models.TextField(blank=True)

    class Meta:
        ordering = ['from_node', 'id']

    def __str__(self):
        return f'{self.from_node.node_key} -> {self.to_node.node_key}'


INSTANCE_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('running', 'Running'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('error', 'Error'),
]


class ProcessInstance(TenantAwareModel, TimeStampedModel):
    """Runtime row created when a definition is launched against a
    business object."""

    code = models.CharField(max_length=30, blank=True)
    definition = models.ForeignKey(
        ProcessDefinition, on_delete=models.PROTECT, related_name='instances',
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wfa_started_instances',
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=INSTANCE_STATUS_CHOICES, default='pending')
    current_node = models.ForeignKey(
        ProcessNode, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='current_instances',
    )
    context_json = models.JSONField(default=dict, blank=True)
    business_object_type = models.CharField(max_length=120, blank=True)
    business_object_id = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'instance-{self.pk}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(ProcessInstance, self.tenant, 'PI')
        super().save(*args, **kwargs)

    def is_active(self):
        return self.status in ('pending', 'running')


VARIABLE_TYPE_CHOICES = [
    ('string', 'String'),
    ('int', 'Integer'),
    ('decimal', 'Decimal'),
    ('bool', 'Boolean'),
    ('date', 'Date'),
]


class ProcessVariable(TenantAwareModel, TimeStampedModel):
    instance = models.ForeignKey(
        ProcessInstance, on_delete=models.CASCADE, related_name='variables',
    )
    name = models.CharField(max_length=80)
    value_text = models.TextField(blank=True)
    value_type = models.CharField(max_length=10, choices=VARIABLE_TYPE_CHOICES, default='string')

    class Meta:
        ordering = ['name']
        unique_together = ('instance', 'name')

    def __str__(self):
        return f'{self.name}={self.value_text[:40]}'


ACTIVITY_EVENT_CHOICES = [
    ('entered', 'Entered'),
    ('completed', 'Completed'),
    ('skipped', 'Skipped'),
    ('error', 'Error'),
    ('cancelled', 'Cancelled'),
]


class ProcessActivity(TenantAwareModel, TimeStampedModel):
    """Append-only execution log."""

    instance = models.ForeignKey(
        ProcessInstance, on_delete=models.PROTECT, related_name='activities',
    )
    node = models.ForeignKey(
        ProcessNode, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='activities',
    )
    event = models.CharField(max_length=15, choices=ACTIVITY_EVENT_CHOICES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wfa_activities',
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-recorded_at']
        verbose_name_plural = 'Process activities'

    def __str__(self):
        return f'{self.instance.code} {self.event}'


# ============================================================================
# 20.2  APPROVAL ENGINE
# ============================================================================

class ApprovalPolicy(TenantAwareModel, TimeStampedModel):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40)
    description = models.TextField(blank=True)
    applies_to_type = models.CharField(
        max_length=120, blank=True,
        help_text='Optional model label such as "procurement.PurchaseOrder" '
                  'so the cross-module hook can pick the policy up automatically.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')
        verbose_name_plural = 'Approval policies'

    def __str__(self):
        return self.name


APPROVER_ROLE_CHOICES = [
    ('department_head', 'Department Head'),
    ('quality_manager', 'Quality Manager'),
    ('compliance_officer', 'Compliance Officer'),
    ('plant_manager', 'Plant Manager'),
    ('cfo', 'CFO'),
    ('cto', 'CTO'),
    ('ceo', 'CEO'),
    ('tenant_admin', 'Tenant Admin'),
    ('custom', 'Custom'),
]


class ApprovalLevel(TenantAwareModel, TimeStampedModel):
    policy = models.ForeignKey(
        ApprovalPolicy, on_delete=models.CASCADE, related_name='levels',
    )
    level_no = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(20)])
    name = models.CharField(max_length=120)
    approver_role = models.CharField(max_length=30, choices=APPROVER_ROLE_CHOICES, default='department_head')
    min_approvers = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(20)])
    sla_hours = models.PositiveIntegerField(default=24, validators=[MinValueValidator(0), MaxValueValidator(8760)])
    allow_delegation = models.BooleanField(default=True)

    class Meta:
        ordering = ['policy', 'level_no']
        unique_together = ('policy', 'level_no')

    def __str__(self):
        return f'{self.policy.code} L{self.level_no} {self.name}'


APPROVAL_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('in_progress', 'In Progress'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Cancelled'),
    ('escalated', 'Escalated'),
]


class ApprovalRequest(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=30, blank=True)
    policy = models.ForeignKey(
        ApprovalPolicy, on_delete=models.PROTECT, related_name='requests',
    )
    current_level_no = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(20)])
    subject = models.CharField(max_length=200)
    business_object_type = models.CharField(max_length=120, blank=True)
    business_object_id = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=APPROVAL_STATUS_CHOICES, default='pending')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wfa_requested_approvals',
    )
    requested_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_at']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'request-{self.pk}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(ApprovalRequest, self.tenant, 'APR')
        super().save(*args, **kwargs)

    def is_open(self):
        return self.status in ('pending', 'in_progress', 'escalated')

    def is_overdue(self):
        return bool(self.due_at and self.is_open() and self.due_at < timezone.now())


class ApprovalDelegation(TenantAwareModel, TimeStampedModel):
    delegator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='wfa_delegations_out',
    )
    delegate = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='wfa_delegations_in',
    )
    policy = models.ForeignKey(
        ApprovalPolicy, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='delegations',
    )
    starts_at = models.DateField()
    ends_at = models.DateField()
    reason = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-starts_at']
        unique_together = ('tenant', 'delegator', 'policy', 'starts_at')

    def __str__(self):
        scope = self.policy.code if self.policy else 'ALL'
        return f'{self.delegator} -> {self.delegate} ({scope})'


ACTION_DECISION_CHOICES = [
    ('submit', 'Submit'),
    ('approve', 'Approve'),
    ('reject', 'Reject'),
    ('delegate', 'Delegate'),
    ('escalate', 'Escalate'),
    ('recall', 'Recall'),
]


class ApprovalActionLog(TenantAwareModel, TimeStampedModel):
    request = models.ForeignKey(
        ApprovalRequest, on_delete=models.PROTECT, related_name='action_logs',
    )
    level_no = models.PositiveIntegerField(default=1)
    decision = models.CharField(max_length=12, choices=ACTION_DECISION_CHOICES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wfa_actions',
    )
    delegated_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wfa_received_delegations',
    )
    decided_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-decided_at']

    def __str__(self):
        return f'{self.request.code} {self.decision} L{self.level_no}'


class EscalationRule(TenantAwareModel, TimeStampedModel):
    policy = models.ForeignKey(
        ApprovalPolicy, on_delete=models.CASCADE, related_name='escalation_rules',
    )
    level_no = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(20)])
    trigger_hours_overdue = models.PositiveIntegerField(default=24, validators=[MinValueValidator(1), MaxValueValidator(720)])
    escalate_to_role = models.CharField(max_length=30, choices=APPROVER_ROLE_CHOICES, default='plant_manager')
    notify_channels = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['policy', 'level_no', 'trigger_hours_overdue']
        unique_together = ('policy', 'level_no', 'trigger_hours_overdue')

    def __str__(self):
        return f'{self.policy.code} L{self.level_no} +{self.trigger_hours_overdue}h'


# ============================================================================
# 20.3  NOTIFICATION & ESCALATION MATRIX
# ============================================================================

CHANNEL_CODE_CHOICES = [
    ('email', 'Email'),
    ('sms', 'SMS (stub)'),
    ('in_app', 'In-App'),
    ('webhook', 'Webhook'),
]


class NotificationChannel(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=20, choices=CHANNEL_CODE_CHOICES)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    config_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.name


class NotificationTemplate(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    event_type = models.CharField(max_length=80)
    subject_template = models.CharField(max_length=255)
    body_template = models.TextField()
    channels = models.JSONField(
        default=list, blank=True,
        help_text='List of channel codes to fan out to: ["email","in_app"]',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['event_type', 'code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} ({self.event_type})'


class NotificationRule(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=200)
    event_type = models.CharField(max_length=80)
    template = models.ForeignKey(
        NotificationTemplate, on_delete=models.PROTECT,
        related_name='rules',
    )
    delay_minutes = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10080)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['event_type', 'code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(NotificationRule, self.tenant, 'NR')
        super().save(*args, **kwargs)


NOTIFICATION_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('sent', 'Sent'),
    ('failed', 'Failed'),
    ('skipped', 'Skipped'),
]


class Notification(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=30, blank=True)
    rule = models.ForeignKey(
        NotificationRule, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='notifications',
    )
    event_type = models.CharField(max_length=80, blank=True)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='wfa_notifications',
    )
    subject = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=NOTIFICATION_STATUS_CHOICES, default='pending')
    payload_json = models.JSONField(default=dict, blank=True)
    triggered_at = models.DateTimeField(default=timezone.now)
    dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-triggered_at']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'ntf-{self.pk}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(Notification, self.tenant, 'NTF')
        super().save(*args, **kwargs)


DELIVERY_STATUS_CHOICES = [
    ('sent', 'Sent'),
    ('failed', 'Failed'),
    ('skipped', 'Skipped'),
]


class NotificationDelivery(TenantAwareModel, TimeStampedModel):
    notification = models.ForeignKey(
        Notification, on_delete=models.PROTECT, related_name='deliveries',
    )
    channel = models.ForeignKey(
        NotificationChannel, on_delete=models.PROTECT, related_name='deliveries',
    )
    status = models.CharField(max_length=10, choices=DELIVERY_STATUS_CHOICES)
    external_ref = models.CharField(max_length=120, blank=True)
    attempted_at = models.DateTimeField(default=timezone.now)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-attempted_at']
        verbose_name_plural = 'Notification deliveries'

    def __str__(self):
        return f'{self.notification.code} -> {self.channel.code} {self.status}'


SMS_STATUS_CHOICES = [
    ('sent_stub', 'Sent (stub)'),
    ('failed', 'Failed'),
]


class SMSDelivery(TenantAwareModel, TimeStampedModel):
    """Stub ledger - mirrors every SMS dispatch without contacting a
    provider. Replace this with a real Twilio adapter when configured.
    """

    notification = models.ForeignKey(
        Notification, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sms_deliveries',
    )
    to_phone = models.CharField(max_length=30)
    body = models.TextField()
    status = models.CharField(max_length=15, choices=SMS_STATUS_CHOICES, default='sent_stub')
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'SMS delivery'
        verbose_name_plural = 'SMS deliveries'

    def __str__(self):
        return f'{self.to_phone} {self.status}'


# ============================================================================
# 20.4  INTEGRATION ORCHESTRATION
# ============================================================================

CONNECTOR_TYPE_CHOICES = [
    ('rest_api', 'REST API'),
    ('webhook', 'Webhook'),
    ('file_drop', 'File Drop (SFTP)'),
    ('db_pull', 'Database Pull'),
    ('erp_sap', 'ERP: SAP'),
    ('erp_oracle', 'ERP: Oracle'),
    ('erp_dynamics', 'ERP: Microsoft Dynamics'),
    ('erp_netsuite', 'ERP: NetSuite'),
    ('crm_salesforce', 'CRM: Salesforce'),
    ('crm_hubspot', 'CRM: HubSpot'),
    ('other', 'Other'),
]

AUTH_METHOD_CHOICES = [
    ('none', 'None'),
    ('basic', 'Basic'),
    ('bearer', 'Bearer Token'),
    ('api_key', 'API Key'),
    ('oauth2', 'OAuth2'),
]


class Connector(TenantAwareModel, TimeStampedModel):
    """Stop-gap secret storage warning: ``auth_secret_hash`` is stored as a
    stable token (similar to ``iot.DeviceBroker.password_hash``). Rotate
    to a KMS / Vault-backed field for production deployments."""

    code = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=200)
    connector_type = models.CharField(max_length=20, choices=CONNECTOR_TYPE_CHOICES, default='rest_api')
    base_url = models.URLField(blank=True)
    auth_method = models.CharField(max_length=10, choices=AUTH_METHOD_CHOICES, default='none')
    auth_secret_hash = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(Connector, self.tenant, 'CON')
        super().save(*args, **kwargs)


HTTP_METHOD_CHOICES = [
    ('GET', 'GET'),
    ('POST', 'POST'),
    ('PUT', 'PUT'),
    ('PATCH', 'PATCH'),
    ('DELETE', 'DELETE'),
]


class ConnectorEndpoint(TenantAwareModel, TimeStampedModel):
    connector = models.ForeignKey(
        Connector, on_delete=models.CASCADE, related_name='endpoints',
    )
    name = models.CharField(max_length=120)
    path = models.CharField(max_length=255)
    method = models.CharField(max_length=6, choices=HTTP_METHOD_CHOICES, default='GET')
    headers_json = models.JSONField(default=dict, blank=True)
    request_template = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['connector', 'name']
        unique_together = ('connector', 'name')

    def __str__(self):
        return f'{self.connector.code}:{self.name}'


TRIGGER_TYPE_CHOICES = [
    ('manual', 'Manual'),
    ('cron', 'Cron Schedule'),
    ('event', 'Internal Event'),
    ('webhook', 'Inbound Webhook'),
]


class IntegrationFlow(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    trigger_type = models.CharField(max_length=10, choices=TRIGGER_TYPE_CHOICES, default='manual')
    trigger_config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.name


STEP_TYPE_CHOICES = [
    ('http_call', 'HTTP Call'),
    ('transform', 'Transform'),
    ('branch', 'Branch (Condition)'),
    ('log', 'Log'),
    ('sleep', 'Sleep / Delay'),
]

ON_FAILURE_CHOICES = [
    ('abort', 'Abort Flow'),
    ('continue', 'Continue'),
    ('retry', 'Retry'),
]


class FlowStep(TenantAwareModel, TimeStampedModel):
    flow = models.ForeignKey(
        IntegrationFlow, on_delete=models.CASCADE, related_name='steps',
    )
    step_no = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(200)])
    name = models.CharField(max_length=120)
    step_type = models.CharField(max_length=12, choices=STEP_TYPE_CHOICES, default='http_call')
    endpoint = models.ForeignKey(
        ConnectorEndpoint, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='flow_steps',
    )
    config_json = models.JSONField(default=dict, blank=True)
    on_failure = models.CharField(max_length=10, choices=ON_FAILURE_CHOICES, default='abort')

    class Meta:
        ordering = ['flow', 'step_no']
        unique_together = ('flow', 'step_no')

    def __str__(self):
        return f'{self.flow.code} #{self.step_no} {self.name}'


RUN_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('running', 'Running'),
    ('completed', 'Completed'),
    ('failed', 'Failed'),
    ('cancelled', 'Cancelled'),
]


class IntegrationRun(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=30, blank=True)
    flow = models.ForeignKey(
        IntegrationFlow, on_delete=models.PROTECT, related_name='runs',
    )
    status = models.CharField(max_length=10, choices=RUN_STATUS_CHOICES, default='pending')
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wfa_triggered_runs',
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    result_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-started_at']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'run-{self.pk}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(IntegrationRun, self.tenant, 'IR')
        super().save(*args, **kwargs)


OUTBOX_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('sent', 'Sent'),
    ('failed', 'Failed'),
    ('retrying', 'Retrying'),
]


class WebhookOutboxEntry(TenantAwareModel, TimeStampedModel):
    flow_run = models.ForeignKey(
        IntegrationRun, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='outbox_entries',
    )
    target_url = models.URLField()
    payload_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=OUTBOX_STATUS_CHOICES, default='pending')
    attempts = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(20)])
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)

    class Meta:
        ordering = ['-id']
        verbose_name_plural = 'Webhook outbox entries'

    def __str__(self):
        return f'{self.target_url[:40]} {self.status}'


# ============================================================================
# 20.5  PROCESS MINING & OPTIMIZATION
# ============================================================================

METRIC_TYPE_CHOICES = [
    ('cycle_time', 'Cycle Time'),
    ('wait_time', 'Wait Time'),
    ('processing_time', 'Processing Time'),
    ('handoff_count', 'Handoff Count'),
]


class ProcessMetric(TenantAwareModel, TimeStampedModel):
    instance = models.ForeignKey(
        ProcessInstance, on_delete=models.CASCADE, related_name='metrics',
    )
    metric_type = models.CharField(max_length=20, choices=METRIC_TYPE_CHOICES)
    value_seconds = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    node = models.ForeignKey(
        ProcessNode, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='metrics',
    )
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-recorded_at']
        unique_together = ('instance', 'metric_type', 'node')

    def __str__(self):
        return f'{self.instance.code} {self.metric_type}={self.value_seconds}s'


SEVERITY_CHOICES = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('critical', 'Critical'),
]


class BottleneckAnalysis(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=30, blank=True)
    definition = models.ForeignKey(
        ProcessDefinition, on_delete=models.PROTECT, related_name='bottlenecks',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    bottleneck_node = models.ForeignKey(
        ProcessNode, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bottlenecks',
    )
    avg_wait_seconds = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    instance_count = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='low')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period_end', '-id']
        unique_together = ('tenant', 'code')
        verbose_name_plural = 'Bottleneck analyses'

    def __str__(self):
        return self.code or f'ba-{self.pk}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(BottleneckAnalysis, self.tenant, 'BA')
        super().save(*args, **kwargs)


SUGGESTION_TYPE_CHOICES = [
    ('reorder_steps', 'Reorder Steps'),
    ('parallelize', 'Parallelize Steps'),
    ('auto_route', 'Auto-Route Decisions'),
    ('remove_step', 'Remove Redundant Step'),
    ('add_validation', 'Add Input Validation'),
]

SUGGESTION_STATUS_CHOICES = [
    ('new', 'New'),
    ('acknowledged', 'Acknowledged'),
    ('dismissed', 'Dismissed'),
    ('applied', 'Applied'),
]


class ProcessOptimizationSuggestion(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=30, blank=True)
    definition = models.ForeignKey(
        ProcessDefinition, on_delete=models.PROTECT,
        related_name='optimization_suggestions',
    )
    analysis = models.ForeignKey(
        BottleneckAnalysis, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='suggestions',
    )
    suggestion_type = models.CharField(max_length=20, choices=SUGGESTION_TYPE_CHOICES)
    description = models.TextField()
    expected_savings_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    status = models.CharField(max_length=15, choices=SUGGESTION_STATUS_CHOICES, default='new')
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wfa_ack_suggestions',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'pos-{self.pk}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(ProcessOptimizationSuggestion, self.tenant, 'POS')
        super().save(*args, **kwargs)


class CycleTimeReport(TenantAwareModel, TimeStampedModel):
    code = models.CharField(max_length=30, blank=True)
    definition = models.ForeignKey(
        ProcessDefinition, on_delete=models.PROTECT, related_name='cycle_reports',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    instance_count = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    avg_cycle_seconds = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    p95_cycle_seconds = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    min_cycle_seconds = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    max_cycle_seconds = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )

    class Meta:
        ordering = ['-period_end', '-id']
        unique_together = ('tenant', 'definition', 'period_start', 'period_end')

    def __str__(self):
        return self.code or f'ctr-{self.pk}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_code(CycleTimeReport, self.tenant, 'CTR')
        super().save(*args, **kwargs)
