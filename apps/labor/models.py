"""Module 11 - Labor & Workforce Management.

Sub-modules:
    11.1  Employee Master & Skills Matrix   (Department, Position, Employee,
                                             Skill, EmployeeSkill, Certification,
                                             EmployeeCertification, EmployeeDocument)
    11.2  Time & Attendance Integration     (Shift, ShiftRoster, AttendanceRecord,
                                             LeaveType, LeaveRequest, Holiday)
    11.3  Labor Cost Allocation             (CostCenter, LaborRate, LaborBooking)
    11.4  Training & Competency Management  (TrainingProgram, TrainingPlan,
                                             TrainingSession, TrainingAttendance,
                                             CompetencyAssessment, CompetencyResult)
    11.5  Incentive & Piece-Rate            (IncentiveScheme, PieceRate,
                                             IncentivePeriod, IncentiveRun,
                                             IncentiveLine)

Cross-module integration (additive, nullable FKs added in mes/eam/plm):
    - apps.mes.ShopFloorOperator.employee  -> labor.Employee
    - apps.eam.Asset.cost_center           -> labor.CostCenter
    - apps.plm.Product.cost_center         -> labor.CostCenter
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# ============================================================================
# 11.1  EMPLOYEE MASTER & SKILLS MATRIX
# ============================================================================

class Department(TenantAwareModel, TimeStampedModel):
    """Org-chart unit (HR, Production, QC, Maintenance, etc.)."""

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='children',
    )
    manager = models.ForeignKey(
        'labor.Employee', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='managed_departments',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class Position(TenantAwareModel, TimeStampedModel):
    """Job title within a department."""

    LEVEL_CHOICES = [
        ('junior', 'Junior'),
        ('mid', 'Mid-level'),
        ('senior', 'Senior'),
        ('lead', 'Lead'),
        ('manager', 'Manager'),
        ('director', 'Director'),
    ]

    title = models.CharField(max_length=120)
    code = models.CharField(max_length=30)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='positions',
    )
    level = models.CharField(max_length=12, choices=LEVEL_CHOICES, default='mid')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.title}'


class Employee(TenantAwareModel, TimeStampedModel):
    """Workforce master record. Auto-numbered EMP-00001."""

    EMPLOYMENT_TYPE_CHOICES = [
        ('permanent', 'Permanent'),
        ('contract', 'Contract'),
        ('temporary', 'Temporary'),
        ('intern', 'Intern'),
    ]
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer_not_to_say', 'Prefer not to say'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('on_leave', 'On Leave'),
        ('suspended', 'Suspended'),
        ('terminated', 'Terminated'),
    ]

    employee_number = models.CharField(max_length=15)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employee_profile',
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='employees',
    )
    position = models.ForeignKey(
        Position, on_delete=models.PROTECT, related_name='employees',
    )
    employment_type = models.CharField(
        max_length=12, choices=EMPLOYMENT_TYPE_CHOICES, default='permanent',
    )
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=20, choices=GENDER_CHOICES, blank=True,
    )
    address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['employee_number']
        unique_together = ('tenant', 'employee_number')

    def __str__(self):
        return f'{self.employee_number} - {self.full_name()}'

    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def save(self, *args, **kwargs):
        if not self.employee_number and self.tenant_id:
            last = (
                Employee.all_objects
                .filter(tenant_id=self.tenant_id)
                .filter(employee_number__startswith='EMP-')
                .order_by('-employee_number')
                .first()
            )
            n = 1
            if last and last.employee_number.startswith('EMP-'):
                try:
                    n = int(last.employee_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.employee_number = f'EMP-{n:05d}'
        super().save(*args, **kwargs)


class Skill(TenantAwareModel, TimeStampedModel):
    """Tenant-level catalog of skills."""

    CATEGORY_CHOICES = [
        ('operations', 'Operations'),
        ('quality', 'Quality'),
        ('safety', 'Safety'),
        ('leadership', 'Leadership'),
        ('technical', 'Technical'),
        ('soft', 'Soft Skills'),
    ]

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30)
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default='operations')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class EmployeeSkill(TenantAwareModel, TimeStampedModel):
    """Employee -> Skill mapping with proficiency."""

    PROFICIENCY_CHOICES = [
        (1, 'Novice'),
        (2, 'Advanced Beginner'),
        (3, 'Competent'),
        (4, 'Proficient'),
        (5, 'Expert'),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='skills',
    )
    skill = models.ForeignKey(
        Skill, on_delete=models.PROTECT, related_name='employee_links',
    )
    proficiency = models.PositiveSmallIntegerField(
        choices=PROFICIENCY_CHOICES, default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    assessed_at = models.DateField(null=True, blank=True)
    assessor = models.ForeignKey(
        Employee, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assessed_skills',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-proficiency', 'skill__code']
        unique_together = ('employee', 'skill')

    def __str__(self):
        return f'{self.employee} | {self.skill} | L{self.proficiency}'


class Certification(TenantAwareModel, TimeStampedModel):
    """Tenant-level catalog of certifications."""

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30)
    issuing_authority = models.CharField(max_length=200, blank=True)
    valid_period_days = models.PositiveIntegerField(
        default=365,
        validators=[MinValueValidator(1), MaxValueValidator(36500)],
        help_text='Default validity (days) when issuing this certification.',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class EmployeeCertification(TenantAwareModel, TimeStampedModel):
    """Per-employee certification record with expiry."""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expiring_soon', 'Expiring Soon'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked'),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='certifications',
    )
    certification = models.ForeignKey(
        Certification, on_delete=models.PROTECT, related_name='employee_records',
    )
    certificate_number = models.CharField(max_length=120)
    issued_at = models.DateField()
    expires_at = models.DateField()
    attachment = models.FileField(
        upload_to='labor/certifications/', blank=True, null=True,
    )
    status = models.CharField(max_length=14, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-expires_at']
        unique_together = ('employee', 'certification', 'certificate_number')

    def __str__(self):
        return f'{self.employee} - {self.certification} ({self.certificate_number})'

    def save(self, *args, **kwargs):
        if self.expires_at and self.status not in ('revoked',):
            today = timezone.now().date()
            if self.expires_at < today:
                self.status = 'expired'
            elif self.expires_at <= today + timedelta(days=30):
                self.status = 'expiring_soon'
            else:
                self.status = 'active'
        super().save(*args, **kwargs)


class EmployeeDocument(TenantAwareModel, TimeStampedModel):
    """Generic uploads (contract, ID scan, etc.)."""

    DOC_TYPE_CHOICES = [
        ('contract', 'Contract'),
        ('id', 'Government ID'),
        ('resume', 'Resume / CV'),
        ('training_cert', 'Training Certificate'),
        ('other', 'Other'),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='documents',
    )
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='other')
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to='labor/employee_documents/')
    description = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.employee} - {self.name}'


# ============================================================================
# 11.2  TIME & ATTENDANCE INTEGRATION
# ============================================================================

class Shift(TenantAwareModel, TimeStampedModel):
    """Shift template (Morning, Evening, Night)."""

    name = models.CharField(max_length=80)
    code = models.CharField(max_length=20)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_minutes = models.PositiveIntegerField(
        default=30, validators=[MinValueValidator(0), MaxValueValidator(480)],
    )
    is_overnight = models.BooleanField(default=False)
    color = models.CharField(max_length=7, default='#3B82F6', help_text='Hex color for the calendar UI.')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class ShiftRoster(TenantAwareModel, TimeStampedModel):
    """Per-employee shift assignment over a date range."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='shift_rosters',
    )
    shift = models.ForeignKey(
        Shift, on_delete=models.PROTECT, related_name='rosters',
    )
    start_date = models.DateField()
    end_date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['tenant', 'employee', 'start_date']),
        ]

    def __str__(self):
        return f'{self.employee} - {self.shift} ({self.start_date} -> {self.end_date})'


class AttendanceRecord(TenantAwareModel, TimeStampedModel):
    """One row per employee per work date."""

    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('half_day', 'Half Day'),
        ('on_leave', 'On Leave'),
        ('holiday', 'Holiday'),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='attendance_records',
    )
    work_date = models.DateField()
    shift = models.ForeignKey(
        Shift, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='attendance_records',
    )
    clock_in_at = models.DateTimeField(null=True, blank=True)
    clock_out_at = models.DateTimeField(null=True, blank=True)
    worked_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='present')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-work_date']
        unique_together = ('employee', 'work_date')
        indexes = [
            models.Index(fields=['tenant', 'work_date', 'status']),
        ]

    def __str__(self):
        return f'{self.employee} | {self.work_date} | {self.get_status_display()}'


class LeaveType(TenantAwareModel, TimeStampedModel):
    """Tenant catalog of leave types."""

    name = models.CharField(max_length=80)
    code = models.CharField(max_length=20)
    paid = models.BooleanField(default=True)
    default_annual_quota_days = models.DecimalField(
        max_digits=5, decimal_places=1, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='0 = unlimited.',
    )
    requires_attachment = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class LeaveRequest(TenantAwareModel, TimeStampedModel):
    """Per-employee leave request."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    request_number = models.CharField(max_length=15)
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='leave_requests',
    )
    leave_type = models.ForeignKey(
        LeaveType, on_delete=models.PROTECT, related_name='requests',
    )
    start_date = models.DateField()
    end_date = models.DateField()
    days_requested = models.DecimalField(
        max_digits=5, decimal_places=1, default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0.5'))],
    )
    reason = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to='labor/leave_requests/', blank=True, null=True,
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='draft')
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'request_number')

    def __str__(self):
        return f'{self.request_number} - {self.employee}'

    def save(self, *args, **kwargs):
        if not self.request_number and self.tenant_id:
            last = (
                LeaveRequest.all_objects
                .filter(tenant_id=self.tenant_id)
                .filter(request_number__startswith='LR-')
                .order_by('-request_number')
                .first()
            )
            n = 1
            if last and last.request_number.startswith('LR-'):
                try:
                    n = int(last.request_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.request_number = f'LR-{n:05d}'
        super().save(*args, **kwargs)


class Holiday(TenantAwareModel, TimeStampedModel):
    """Tenant calendar of paid holidays."""

    name = models.CharField(max_length=120)
    holiday_date = models.DateField()
    is_recurring = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['holiday_date']
        unique_together = ('tenant', 'holiday_date')

    def __str__(self):
        return f'{self.holiday_date} - {self.name}'


# ============================================================================
# 11.3  LABOR COST ALLOCATION
# ============================================================================

class CostCenter(TenantAwareModel, TimeStampedModel):
    """Cost center for labor + overhead allocation."""

    CC_TYPE_CHOICES = [
        ('production', 'Production'),
        ('quality', 'Quality'),
        ('maintenance', 'Maintenance'),
        ('admin', 'Administrative'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='children',
    )
    cc_type = models.CharField(max_length=12, choices=CC_TYPE_CHOICES, default='production')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class LaborRate(TenantAwareModel, TimeStampedModel):
    """Hourly rate for an employee for a date range."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='labor_rates',
    )
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    overtime_multiplier = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal('1.50'),
        validators=[MinValueValidator(Decimal('1.00')), MaxValueValidator(Decimal('3.00'))],
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-effective_from']
        indexes = [
            models.Index(fields=['tenant', 'employee', '-effective_from']),
        ]

    def __str__(self):
        return f'{self.employee} | {self.hourly_rate} from {self.effective_from}'


class LaborBooking(TenantAwareModel, TimeStampedModel):
    """Append-only labor cost ledger.

    PROTECT FK on Employee per Lesson L-17 - audit-trail integrity.
    """

    KIND_CHOICES = [
        ('direct', 'Direct'),
        ('indirect', 'Indirect'),
        ('overtime', 'Overtime'),
        ('idle', 'Idle'),
    ]
    SOURCE_TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('mes_time_log', 'MES Time Log'),
        ('eam_mwo_labor', 'EAM MWO Labor'),
    ]

    booking_number = models.CharField(max_length=15)
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name='labor_bookings',
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='direct')
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='labor_bookings',
    )
    worked_at = models.DateTimeField()
    minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    hourly_rate_snapshot = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    source_type = models.CharField(
        max_length=15, choices=SOURCE_TYPE_CHOICES, default='manual',
    )
    source_time_log = models.ForeignKey(
        'mes.OperatorTimeLog', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='labor_bookings',
    )
    source_mwo_labor = models.ForeignKey(
        'eam.MWOLaborLog', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='labor_bookings',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-worked_at']
        unique_together = ('tenant', 'booking_number')
        indexes = [
            models.Index(fields=['tenant', 'employee', '-worked_at']),
            models.Index(fields=['tenant', 'cost_center', '-worked_at']),
            models.Index(fields=['tenant', 'kind', '-worked_at']),
        ]

    def __str__(self):
        return f'{self.booking_number} | {self.employee} | {self.minutes}m | {self.total_cost}'

    def save(self, *args, **kwargs):
        if not self.booking_number and self.tenant_id:
            last = (
                LaborBooking.all_objects
                .filter(tenant_id=self.tenant_id)
                .filter(booking_number__startswith='LB-')
                .order_by('-booking_number')
                .first()
            )
            n = 1
            if last and last.booking_number.startswith('LB-'):
                try:
                    n = int(last.booking_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.booking_number = f'LB-{n:05d}'
        if self.minutes and self.hourly_rate_snapshot is not None:
            self.total_cost = (
                Decimal(self.minutes) * self.hourly_rate_snapshot / Decimal('60')
            ).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


# ============================================================================
# 11.4  TRAINING & COMPETENCY MANAGEMENT
# ============================================================================

class TrainingProgram(TenantAwareModel, TimeStampedModel):
    """Tenant catalog of training programs."""

    DELIVERY_MODE_CHOICES = [
        ('classroom', 'Classroom'),
        ('online', 'Online'),
        ('on_the_job', 'On-the-Job'),
        ('external', 'External'),
    ]

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30)
    description = models.TextField(blank=True)
    delivery_mode = models.CharField(
        max_length=12, choices=DELIVERY_MODE_CHOICES, default='classroom',
    )
    duration_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.5'))],
    )
    competency_target = models.ForeignKey(
        Skill, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='training_programs',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class TrainingPlan(TenantAwareModel, TimeStampedModel):
    """Per-employee training assignment."""

    STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('waived', 'Waived'),
        ('overdue', 'Overdue'),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='training_plans',
    )
    program = models.ForeignKey(
        TrainingProgram, on_delete=models.PROTECT, related_name='plans',
    )
    target_completion_date = models.DateField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='assigned')
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-target_completion_date']
        unique_together = ('employee', 'program', 'target_completion_date')

    def __str__(self):
        return f'{self.employee} | {self.program} | {self.get_status_display()}'


class TrainingSession(TenantAwareModel, TimeStampedModel):
    """A scheduled instance of a training program."""

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    session_number = models.CharField(max_length=15)
    program = models.ForeignKey(
        TrainingProgram, on_delete=models.PROTECT, related_name='sessions',
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    instructor = models.ForeignKey(
        Employee, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='led_sessions',
    )
    capacity = models.PositiveIntegerField(
        default=20, validators=[MinValueValidator(1)],
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_at']
        unique_together = ('tenant', 'session_number')

    def __str__(self):
        return f'{self.session_number} - {self.program}'

    def save(self, *args, **kwargs):
        if not self.session_number and self.tenant_id:
            last = (
                TrainingSession.all_objects
                .filter(tenant_id=self.tenant_id)
                .filter(session_number__startswith='TS-')
                .order_by('-session_number')
                .first()
            )
            n = 1
            if last and last.session_number.startswith('TS-'):
                try:
                    n = int(last.session_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.session_number = f'TS-{n:05d}'
        super().save(*args, **kwargs)


class TrainingAttendance(TenantAwareModel, TimeStampedModel):
    """Per-attendee record for a session."""

    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name='attendees',
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='training_attendance',
    )
    attended = models.BooleanField(default=False)
    score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    feedback = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['employee__employee_number']
        unique_together = ('session', 'employee')

    def __str__(self):
        return f'{self.session} | {self.employee} | {"Yes" if self.attended else "No"}'


class CompetencyAssessment(TenantAwareModel, TimeStampedModel):
    """Per-employee competency evaluation event. Auto-numbered CA-00001."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('completed', 'Completed'),
    ]

    assessment_number = models.CharField(max_length=15)
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='competency_assessments',
    )
    position = models.ForeignKey(
        Position, on_delete=models.PROTECT, related_name='competency_assessments',
    )
    assessed_at = models.DateField()
    assessor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    overall_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-assessed_at']
        unique_together = ('tenant', 'assessment_number')

    def __str__(self):
        return f'{self.assessment_number} - {self.employee}'

    def save(self, *args, **kwargs):
        if not self.assessment_number and self.tenant_id:
            last = (
                CompetencyAssessment.all_objects
                .filter(tenant_id=self.tenant_id)
                .filter(assessment_number__startswith='CA-')
                .order_by('-assessment_number')
                .first()
            )
            n = 1
            if last and last.assessment_number.startswith('CA-'):
                try:
                    n = int(last.assessment_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.assessment_number = f'CA-{n:05d}'
        super().save(*args, **kwargs)


class CompetencyResult(TenantAwareModel, TimeStampedModel):
    """Per-skill row inside a competency assessment."""

    assessment = models.ForeignKey(
        CompetencyAssessment, on_delete=models.CASCADE, related_name='results',
    )
    skill = models.ForeignKey(
        Skill, on_delete=models.PROTECT, related_name='competency_results',
    )
    expected_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    actual_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    gap = models.SmallIntegerField(default=0, help_text='expected_level - actual_level')
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ['skill__code']
        unique_together = ('assessment', 'skill')

    def __str__(self):
        return f'{self.assessment} | {self.skill} | gap={self.gap}'

    def save(self, *args, **kwargs):
        self.gap = int(self.expected_level) - int(self.actual_level)
        super().save(*args, **kwargs)


# ============================================================================
# 11.5  INCENTIVE & PIECE-RATE CALCULATION
# ============================================================================

class IncentiveScheme(TenantAwareModel, TimeStampedModel):
    """Tenant-level incentive scheme."""

    SCHEME_TYPE_CHOICES = [
        ('piece_rate', 'Piece Rate'),
        ('production_bonus', 'Production Bonus'),
        ('quality_bonus', 'Quality Bonus'),
        ('attendance_bonus', 'Attendance Bonus'),
    ]

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30)
    scheme_type = models.CharField(
        max_length=20, choices=SCHEME_TYPE_CHOICES, default='piece_rate',
    )
    applicable_employees = models.ManyToManyField(
        Employee, blank=True, related_name='incentive_schemes',
    )
    applicable_products = models.ManyToManyField(
        'plm.Product', blank=True, related_name='incentive_schemes',
    )
    applicable_positions = models.ManyToManyField(
        Position, blank=True, related_name='incentive_schemes',
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class PieceRate(TenantAwareModel, TimeStampedModel):
    """Per-product or per-operation rate row inside a scheme."""

    scheme = models.ForeignKey(
        IncentiveScheme, on_delete=models.CASCADE, related_name='piece_rates',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT,
        null=True, blank=True, related_name='piece_rates',
    )
    operation = models.ForeignKey(
        'pps.RoutingOperation', on_delete=models.PROTECT,
        null=True, blank=True, related_name='piece_rates',
    )
    rate_per_unit = models.DecimalField(
        max_digits=10, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    min_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    max_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['scheme__code', 'product__sku']

    def __str__(self):
        target = self.product or self.operation or 'unspecified'
        return f'{self.scheme} | {target} @ {self.rate_per_unit}'


class IncentivePeriod(TenantAwareModel, TimeStampedModel):
    """Calculation window (typically monthly)."""

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('locked', 'Locked'),
        ('paid', 'Paid'),
    ]

    name = models.CharField(max_length=80)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date']
        unique_together = ('tenant', 'start_date', 'end_date')

    def __str__(self):
        return f'{self.name} ({self.start_date} -> {self.end_date})'


class IncentiveRun(TenantAwareModel, TimeStampedModel):
    """Per-period batch calculation. Auto-numbered INC-00001."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('discarded', 'Discarded'),
    ]

    run_number = models.CharField(max_length=15)
    period = models.ForeignKey(
        IncentivePeriod, on_delete=models.PROTECT, related_name='runs',
    )
    scheme = models.ForeignKey(
        IncentiveScheme, on_delete=models.PROTECT, related_name='runs',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'run_number')

    def __str__(self):
        return f'{self.run_number} - {self.scheme} - {self.period}'

    def save(self, *args, **kwargs):
        if not self.run_number and self.tenant_id:
            last = (
                IncentiveRun.all_objects
                .filter(tenant_id=self.tenant_id)
                .filter(run_number__startswith='INC-')
                .order_by('-run_number')
                .first()
            )
            n = 1
            if last and last.run_number.startswith('INC-'):
                try:
                    n = int(last.run_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.run_number = f'INC-{n:05d}'
        super().save(*args, **kwargs)


class IncentiveLine(TenantAwareModel, TimeStampedModel):
    """Per-employee line within a run."""

    run = models.ForeignKey(
        IncentiveRun, on_delete=models.CASCADE, related_name='lines',
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name='incentive_lines',
    )
    qualifying_units = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    rate_applied = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    production_reports = models.ManyToManyField(
        'mes.ProductionReport', blank=True, related_name='incentive_lines',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['employee__employee_number']
        unique_together = ('run', 'employee')

    def __str__(self):
        return f'{self.run} | {self.employee} | {self.amount}'

    def save(self, *args, **kwargs):
        if self.qualifying_units is not None and self.rate_applied is not None:
            self.amount = (self.qualifying_units * self.rate_applied).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
