"""Module 11 - Labor & Workforce Management ModelForms.

Honors:
    - Lesson L-01: forms whose Meta.fields excludes ``tenant`` enforce their
      own ``(tenant, ...)`` unique_together via clean().
    - Lesson L-02: every Decimal field carries explicit MinValueValidator
      (and MaxValueValidator where natural).
    - Lesson L-14: per-workflow forms enforce per-transition required fields.
"""
from datetime import date
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from . import models

ATTACHMENT_ALLOWED_EXT = ['pdf', 'png', 'jpg', 'jpeg']
ATTACHMENT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def _check_attachment(f):
    if f is None:
        return
    if hasattr(f, 'size') and f.size > ATTACHMENT_MAX_BYTES:
        raise ValidationError('Attachment exceeds 25 MB limit.')


# ============================================================================
# Tenant-aware ModelForm base
# ============================================================================

class TenantForm(forms.ModelForm):
    """Stash request.tenant in self._tenant for clean() use (Lesson L-01)."""

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant


# ============================================================================
# 11.1  Employee Master & Skills Matrix
# ============================================================================

class DepartmentForm(TenantForm):
    class Meta:
        model = models.Department
        fields = ['name', 'code', 'parent', 'manager', 'description', 'is_active']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.Department.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A department with this code already exists.')
        return data


class PositionForm(TenantForm):
    class Meta:
        model = models.Position
        fields = ['title', 'code', 'department', 'level', 'description', 'is_active']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.Position.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A position with this code already exists.')
        return data


class EmployeeForm(TenantForm):
    class Meta:
        model = models.Employee
        fields = [
            'user', 'first_name', 'last_name', 'email', 'phone',
            'department', 'position', 'employment_type',
            'hire_date', 'dob', 'gender',
            'address', 'emergency_contact_name', 'emergency_contact_phone',
            'status', 'notes',
        ]
        widgets = {
            'hire_date': forms.DateInput(attrs={'type': 'date'}),
            'dob': forms.DateInput(attrs={'type': 'date'}),
        }


class SkillForm(TenantForm):
    class Meta:
        model = models.Skill
        fields = ['name', 'code', 'category', 'description', 'is_active']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.Skill.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A skill with this code already exists.')
        return data


class EmployeeSkillForm(TenantForm):
    class Meta:
        model = models.EmployeeSkill
        fields = ['skill', 'proficiency', 'assessed_at', 'assessor', 'notes']
        widgets = {'assessed_at': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._employee = employee
        if self._tenant:
            self.fields['skill'].queryset = models.Skill.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
            self.fields['assessor'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant, status='active',
            )

    def clean(self):
        data = super().clean()
        skill = data.get('skill')
        if self._employee and skill:
            qs = models.EmployeeSkill.all_objects.filter(
                employee=self._employee, skill=skill,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('skill', 'This skill is already mapped to the employee.')
        return data


class CertificationForm(TenantForm):
    class Meta:
        model = models.Certification
        fields = ['name', 'code', 'issuing_authority', 'valid_period_days',
                  'description', 'is_active']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.Certification.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A certification with this code already exists.')
        return data


class EmployeeCertificationForm(TenantForm):
    class Meta:
        model = models.EmployeeCertification
        fields = ['certification', 'certificate_number', 'issued_at', 'expires_at',
                  'attachment', 'notes']
        widgets = {
            'issued_at': forms.DateInput(attrs={'type': 'date'}),
            'expires_at': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._employee = employee
        if self._tenant:
            self.fields['certification'].queryset = models.Certification.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean_attachment(self):
        f = self.cleaned_data.get('attachment')
        _check_attachment(f)
        if f and hasattr(f, 'name'):
            ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
            if ext and ext not in ATTACHMENT_ALLOWED_EXT:
                raise ValidationError(
                    f'Allowed attachment types: {", ".join(ATTACHMENT_ALLOWED_EXT)}.'
                )
        return f

    def clean(self):
        data = super().clean()
        cert = data.get('certification')
        cert_num = data.get('certificate_number')
        if self._employee and cert and cert_num:
            qs = models.EmployeeCertification.all_objects.filter(
                employee=self._employee, certification=cert,
                certificate_number=cert_num,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'certificate_number',
                    'A record with this certification + number already exists.'
                )
        return data


class EmployeeDocumentForm(TenantForm):
    class Meta:
        model = models.EmployeeDocument
        fields = ['doc_type', 'name', 'file', 'description']

    def clean_file(self):
        f = self.cleaned_data.get('file')
        _check_attachment(f)
        return f


# ============================================================================
# 11.2  Time & Attendance
# ============================================================================

class ShiftForm(TenantForm):
    class Meta:
        model = models.Shift
        fields = ['name', 'code', 'start_time', 'end_time', 'break_minutes',
                  'is_overnight', 'color', 'is_active', 'notes']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.Shift.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A shift with this code already exists.')
        return data


class ShiftRosterForm(TenantForm):
    class Meta:
        model = models.ShiftRoster
        fields = ['employee', 'shift', 'start_date', 'end_date', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['employee'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant, status='active',
            )
            self.fields['shift'].queryset = models.Shift.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean(self):
        data = super().clean()
        start, end = data.get('start_date'), data.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'End date must be on or after start date.')
        return data


class AttendanceRecordForm(TenantForm):
    class Meta:
        model = models.AttendanceRecord
        fields = ['employee', 'work_date', 'shift', 'clock_in_at',
                  'clock_out_at', 'status', 'notes']
        widgets = {
            'work_date': forms.DateInput(attrs={'type': 'date'}),
            'clock_in_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'clock_out_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['employee'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['shift'].queryset = models.Shift.all_objects.filter(
                tenant=self._tenant,
            )

    def clean(self):
        data = super().clean()
        emp, work_date = data.get('employee'), data.get('work_date')
        if emp and work_date:
            qs = models.AttendanceRecord.all_objects.filter(
                employee=emp, work_date=work_date,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'work_date',
                    'An attendance record already exists for this employee on this date.'
                )
        return data


class LeaveTypeForm(TenantForm):
    class Meta:
        model = models.LeaveType
        fields = ['name', 'code', 'paid', 'default_annual_quota_days',
                  'requires_attachment', 'is_active', 'description']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.LeaveType.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A leave type with this code already exists.')
        return data


class LeaveRequestForm(TenantForm):
    class Meta:
        model = models.LeaveRequest
        fields = ['employee', 'leave_type', 'start_date', 'end_date',
                  'days_requested', 'reason', 'attachment']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['employee'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant, status='active',
            )
            self.fields['leave_type'].queryset = models.LeaveType.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean_attachment(self):
        f = self.cleaned_data.get('attachment')
        _check_attachment(f)
        return f

    def clean(self):
        data = super().clean()
        start, end = data.get('start_date'), data.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'End date must be on or after start date.')
        leave_type = data.get('leave_type')
        attach = data.get('attachment')
        if leave_type and getattr(leave_type, 'requires_attachment', False) and not attach:
            self.add_error('attachment', 'This leave type requires an attachment.')
        return data


class LeaveDecisionForm(forms.Form):
    """Workflow form for approve/reject/cancel (Lesson L-14).

    `mode` is one of 'approve', 'reject', 'cancel'. Reject + cancel of
    already-approved leave both require non-empty decision_notes.
    """
    decision_notes = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, *args, mode='approve', was_approved=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.was_approved = was_approved

    def clean_decision_notes(self):
        notes = (self.cleaned_data.get('decision_notes') or '').strip()
        if self.mode == 'reject' and not notes:
            raise ValidationError('A reason is required to reject a leave request.')
        if self.mode == 'cancel' and self.was_approved and not notes:
            raise ValidationError(
                'A reason is required to cancel a previously approved leave.'
            )
        return notes


class HolidayForm(TenantForm):
    class Meta:
        model = models.Holiday
        fields = ['name', 'holiday_date', 'is_recurring', 'description']
        widgets = {'holiday_date': forms.DateInput(attrs={'type': 'date'})}

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        d = data.get('holiday_date')
        if d:
            qs = models.Holiday.all_objects.filter(tenant=self._tenant, holiday_date=d)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('holiday_date', 'A holiday already exists on this date.')
        return data


# ============================================================================
# 11.3  Labor Cost Allocation
# ============================================================================

class CostCenterForm(TenantForm):
    class Meta:
        model = models.CostCenter
        fields = ['name', 'code', 'parent', 'cc_type', 'description', 'is_active']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.CostCenter.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A cost center with this code already exists.')
        return data


class LaborRateForm(TenantForm):
    class Meta:
        model = models.LaborRate
        fields = ['employee', 'hourly_rate', 'overtime_multiplier',
                  'effective_from', 'effective_to', 'notes']
        widgets = {
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['employee'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant,
            )

    def clean(self):
        data = super().clean()
        ef, et = data.get('effective_from'), data.get('effective_to')
        if ef and et and et < ef:
            self.add_error(
                'effective_to', 'Effective-to must be on or after effective-from.'
            )
        return data


class LaborBookingForm(TenantForm):
    class Meta:
        model = models.LaborBooking
        fields = ['employee', 'kind', 'cost_center', 'worked_at', 'minutes',
                  'hourly_rate_snapshot', 'notes']
        widgets = {
            'worked_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['employee'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['cost_center'].queryset = models.CostCenter.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )


# ============================================================================
# 11.4  Training & Competency
# ============================================================================

class TrainingProgramForm(TenantForm):
    class Meta:
        model = models.TrainingProgram
        fields = ['name', 'code', 'description', 'delivery_mode',
                  'duration_hours', 'competency_target', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['competency_target'].queryset = models.Skill.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.TrainingProgram.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A program with this code already exists.')
        return data


class TrainingPlanForm(TenantForm):
    class Meta:
        model = models.TrainingPlan
        fields = ['employee', 'program', 'target_completion_date', 'status', 'notes']
        widgets = {
            'target_completion_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['employee'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant, status='active',
            )
            self.fields['program'].queryset = models.TrainingProgram.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )


class TrainingPlanWaiveForm(forms.Form):
    """Lesson L-14: Waive requires non-empty notes."""
    notes = forms.CharField(widget=forms.Textarea, required=True,
                            error_messages={'required': 'A reason is required to waive a training plan.'})


class TrainingSessionForm(TenantForm):
    class Meta:
        model = models.TrainingSession
        fields = ['program', 'start_at', 'end_at', 'location', 'instructor',
                  'capacity', 'notes']
        widgets = {
            'start_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['program'].queryset = models.TrainingProgram.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
            self.fields['instructor'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant,
            )

    def clean(self):
        data = super().clean()
        s, e = data.get('start_at'), data.get('end_at')
        if s and e and e <= s:
            self.add_error('end_at', 'End must be after start.')
        return data


class TrainingAttendanceForm(TenantForm):
    class Meta:
        model = models.TrainingAttendance
        fields = ['employee', 'attended', 'score', 'feedback']

    def __init__(self, *args, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = session
        if self._tenant:
            self.fields['employee'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant,
            )

    def clean(self):
        data = super().clean()
        emp = data.get('employee')
        if self._session and emp:
            qs = models.TrainingAttendance.all_objects.filter(
                session=self._session, employee=emp,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('employee', 'This employee is already attending this session.')
        return data


class CompetencyAssessmentForm(TenantForm):
    class Meta:
        model = models.CompetencyAssessment
        fields = ['employee', 'position', 'assessed_at', 'notes']
        widgets = {'assessed_at': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['employee'].queryset = models.Employee.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['position'].queryset = models.Position.all_objects.filter(
                tenant=self._tenant,
            )


class CompetencyAssessmentCompleteForm(forms.Form):
    """Lesson L-14: Complete requires at least one CompetencyResult row.

    The view passes ``has_results`` so the form can validate it.
    """
    def __init__(self, *args, has_results=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._has_results = has_results

    def clean(self):
        data = super().clean()
        if not self._has_results:
            raise ValidationError(
                'At least one competency result is required before completing.'
            )
        return data


class CompetencyResultForm(TenantForm):
    class Meta:
        model = models.CompetencyResult
        fields = ['skill', 'expected_level', 'actual_level', 'comments']

    def __init__(self, *args, assessment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._assessment = assessment
        if self._tenant:
            self.fields['skill'].queryset = models.Skill.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean(self):
        data = super().clean()
        skill = data.get('skill')
        if self._assessment and skill:
            qs = models.CompetencyResult.all_objects.filter(
                assessment=self._assessment, skill=skill,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('skill', 'This skill already has a result for this assessment.')
        return data


# ============================================================================
# 11.5  Incentive & Piece-Rate
# ============================================================================

class IncentiveSchemeForm(TenantForm):
    class Meta:
        model = models.IncentiveScheme
        fields = ['name', 'code', 'scheme_type', 'effective_from', 'effective_to',
                  'is_active', 'notes']
        widgets = {
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.IncentiveScheme.all_objects.filter(
                tenant=self._tenant, code=code,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A scheme with this code already exists.')
        return data


class PieceRateForm(TenantForm):
    class Meta:
        model = models.PieceRate
        fields = ['product', 'operation', 'rate_per_unit',
                  'min_quantity', 'max_quantity', 'notes']

    def __init__(self, *args, scheme=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._scheme = scheme

    def clean(self):
        data = super().clean()
        product = data.get('product')
        op = data.get('operation')
        if not product and not op:
            raise ValidationError('Either product or operation must be set on a piece rate.')
        max_q = data.get('max_quantity')
        min_q = data.get('min_quantity') or Decimal('0')
        if max_q is not None and min_q is not None and max_q <= min_q:
            self.add_error('max_quantity', 'Max quantity must be greater than min quantity.')
        return data


class IncentivePeriodForm(TenantForm):
    class Meta:
        model = models.IncentivePeriod
        fields = ['name', 'start_date', 'end_date', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        s, e = data.get('start_date'), data.get('end_date')
        if s and e and e < s:
            self.add_error('end_date', 'End must be on or after start.')
        if s and e:
            qs = models.IncentivePeriod.all_objects.filter(
                tenant=self._tenant, start_date=s, end_date=e,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('end_date', 'A period with this date range already exists.')
        return data


class IncentiveRunForm(TenantForm):
    class Meta:
        model = models.IncentiveRun
        fields = ['period', 'scheme', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['period'].queryset = models.IncentivePeriod.all_objects.filter(
                tenant=self._tenant, status='open',
            )
            self.fields['scheme'].queryset = models.IncentiveScheme.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
