from django.contrib import admin

from . import models


@admin.register(models.Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'parent', 'manager', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(models.Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'department', 'level', 'is_active', 'tenant')
    list_filter = ('level', 'is_active', 'tenant')
    search_fields = ('code', 'title')


@admin.register(models.Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_number', 'first_name', 'last_name', 'department',
                    'position', 'employment_type', 'status', 'tenant')
    list_filter = ('status', 'employment_type', 'tenant')
    search_fields = ('employee_number', 'first_name', 'last_name', 'email')
    readonly_fields = ('employee_number',)


@admin.register(models.Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'is_active', 'tenant')
    list_filter = ('category', 'is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(models.EmployeeSkill)
class EmployeeSkillAdmin(admin.ModelAdmin):
    list_display = ('employee', 'skill', 'proficiency', 'tenant')
    list_filter = ('proficiency', 'tenant')


@admin.register(models.Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'issuing_authority', 'valid_period_days', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(models.EmployeeCertification)
class EmployeeCertificationAdmin(admin.ModelAdmin):
    list_display = ('employee', 'certification', 'certificate_number',
                    'issued_at', 'expires_at', 'status', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('certificate_number',)


@admin.register(models.EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'doc_type', 'name', 'tenant')
    list_filter = ('doc_type', 'tenant')


@admin.register(models.Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'start_time', 'end_time', 'break_minutes',
                    'is_overnight', 'is_active', 'tenant')
    list_filter = ('is_active', 'is_overnight', 'tenant')
    search_fields = ('code', 'name')


@admin.register(models.ShiftRoster)
class ShiftRosterAdmin(admin.ModelAdmin):
    list_display = ('employee', 'shift', 'start_date', 'end_date', 'tenant')
    list_filter = ('tenant',)


@admin.register(models.AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'work_date', 'shift', 'status',
                    'worked_minutes', 'tenant')
    list_filter = ('status', 'tenant')


@admin.register(models.LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'paid', 'default_annual_quota_days',
                    'is_active', 'tenant')
    list_filter = ('paid', 'is_active', 'tenant')


@admin.register(models.LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('request_number', 'employee', 'leave_type',
                    'start_date', 'end_date', 'status', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('request_number',)
    readonly_fields = ('request_number',)


@admin.register(models.Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ('holiday_date', 'name', 'is_recurring', 'tenant')
    list_filter = ('is_recurring', 'tenant')


@admin.register(models.CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'cc_type', 'parent', 'is_active', 'tenant')
    list_filter = ('cc_type', 'is_active', 'tenant')


@admin.register(models.LaborRate)
class LaborRateAdmin(admin.ModelAdmin):
    list_display = ('employee', 'hourly_rate', 'overtime_multiplier',
                    'effective_from', 'effective_to', 'tenant')
    list_filter = ('tenant',)


@admin.register(models.LaborBooking)
class LaborBookingAdmin(admin.ModelAdmin):
    list_display = ('booking_number', 'employee', 'kind', 'cost_center',
                    'minutes', 'total_cost', 'source_type', 'tenant')
    list_filter = ('kind', 'source_type', 'tenant')
    readonly_fields = ('booking_number', 'total_cost')


@admin.register(models.TrainingProgram)
class TrainingProgramAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'delivery_mode', 'duration_hours', 'is_active', 'tenant')
    list_filter = ('delivery_mode', 'is_active', 'tenant')


@admin.register(models.TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    list_display = ('employee', 'program', 'target_completion_date', 'status', 'tenant')
    list_filter = ('status', 'tenant')


@admin.register(models.TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ('session_number', 'program', 'start_at', 'end_at',
                    'instructor', 'status', 'tenant')
    list_filter = ('status', 'tenant')
    readonly_fields = ('session_number',)


@admin.register(models.TrainingAttendance)
class TrainingAttendanceAdmin(admin.ModelAdmin):
    list_display = ('session', 'employee', 'attended', 'score', 'tenant')
    list_filter = ('attended', 'tenant')


@admin.register(models.CompetencyAssessment)
class CompetencyAssessmentAdmin(admin.ModelAdmin):
    list_display = ('assessment_number', 'employee', 'position',
                    'assessed_at', 'overall_score', 'status', 'tenant')
    list_filter = ('status', 'tenant')
    readonly_fields = ('assessment_number',)


@admin.register(models.CompetencyResult)
class CompetencyResultAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'skill', 'expected_level', 'actual_level', 'gap', 'tenant')
    list_filter = ('tenant',)


@admin.register(models.IncentiveScheme)
class IncentiveSchemeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'scheme_type', 'effective_from', 'effective_to',
                    'is_active', 'tenant')
    list_filter = ('scheme_type', 'is_active', 'tenant')


@admin.register(models.PieceRate)
class PieceRateAdmin(admin.ModelAdmin):
    list_display = ('scheme', 'product', 'operation', 'rate_per_unit', 'tenant')
    list_filter = ('tenant',)


@admin.register(models.IncentivePeriod)
class IncentivePeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'status', 'tenant')
    list_filter = ('status', 'tenant')


@admin.register(models.IncentiveRun)
class IncentiveRunAdmin(admin.ModelAdmin):
    list_display = ('run_number', 'period', 'scheme', 'status',
                    'total_amount', 'tenant')
    list_filter = ('status', 'tenant')
    readonly_fields = ('run_number', 'total_amount')


@admin.register(models.IncentiveLine)
class IncentiveLineAdmin(admin.ModelAdmin):
    list_display = ('run', 'employee', 'qualifying_units', 'rate_applied',
                    'amount', 'tenant')
    list_filter = ('tenant',)
