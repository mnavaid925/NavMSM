"""Module 11 - Labor & Workforce Management views.

Read-only surfaces use ``TenantRequiredMixin`` (Lesson L-10).
State-changing surfaces (workflow transitions, deletes, admin CRUD) use
``TenantAdminRequiredMixin``.

Workflow transitions use a conditional ``UPDATE ... WHERE status IN (...)``
for race safety (Lessons L-03, L-12).
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin

from . import forms, models
from .services import (
    attendance as attendance_svc,
    competency as competency_svc,
    cost_allocation as cost_svc,
    piece_rate as piece_rate_svc,
)

PAGE_SIZE = 25


def _paginate(qs, request, size=PAGE_SIZE):
    paginator = Paginator(qs, size)
    page = request.GET.get('page', 1)
    try:
        return paginator.page(page)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def _atomic_status_transition(model, pk, tenant, from_states, to_state, extra_fields=None):
    fields = {'status': to_state}
    if extra_fields:
        fields.update(extra_fields)
    with transaction.atomic():
        rowcount = model.objects.filter(
            pk=pk, tenant=tenant, status__in=from_states,
        ).update(**fields)
    return rowcount > 0


# ============================================================================
# Dashboard
# ============================================================================

class IndexView(TenantRequiredMixin, View):
    template_name = 'labor/index.html'

    def get(self, request):
        t = request.tenant
        today = timezone.now().date()
        month_start = today.replace(day=1)
        soon = today + timedelta(days=30)

        attendance_30d = (
            models.AttendanceRecord.objects.filter(
                tenant=t, work_date__gte=today - timedelta(days=29),
                work_date__lte=today,
            )
            .values('work_date', 'status')
            .annotate(c=Count('id'))
            .order_by('work_date')
        )
        att_by_date = defaultdict(lambda: {'present': 0, 'total': 0})
        for row in attendance_30d:
            d = row['work_date'].isoformat()
            att_by_date[d]['total'] += row['c']
            if row['status'] in ('present', 'late', 'half_day'):
                att_by_date[d]['present'] += row['c']
        attendance_series = sorted(att_by_date.items())
        att_chart = {
            'dates': [d for d, _ in attendance_series],
            'pct': [
                round((v['present'] / v['total']) * 100, 1) if v['total'] else 0
                for _, v in attendance_series
            ],
        }

        cc_rows = (
            models.LaborBooking.objects.filter(
                tenant=t, worked_at__date__gte=month_start,
            )
            .values('cost_center__name')
            .annotate(total=Sum('total_cost'))
            .order_by('-total')[:8]
        )
        cc_chart = {
            'labels': [r['cost_center__name'] or 'Unallocated' for r in cc_rows],
            'values': [float(r['total'] or 0) for r in cc_rows],
        }

        ctx = {
            'employee_count': models.Employee.objects.filter(
                tenant=t, status='active',
            ).count(),
            'on_leave_today': models.LeaveRequest.objects.filter(
                tenant=t, status='approved',
                start_date__lte=today, end_date__gte=today,
            ).count(),
            'expiring_certs': models.EmployeeCertification.objects.filter(
                tenant=t, expires_at__lte=soon, expires_at__gte=today,
            ).count(),
            'expired_certs': models.EmployeeCertification.objects.filter(
                tenant=t, expires_at__lt=today,
            ).count(),
            'pending_leaves': models.LeaveRequest.objects.filter(
                tenant=t, status='submitted',
            ).count(),
            'open_runs': models.IncentiveRun.objects.filter(
                tenant=t, status__in=('draft', 'running'),
            ).count(),
            'incentive_total_month': models.IncentiveRun.objects.filter(
                tenant=t, status='completed',
                period__start_date__lte=today, period__end_date__gte=month_start,
            ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0'),
            'recent_employees': models.Employee.objects.filter(tenant=t).order_by('-id')[:6],
            'recent_leaves': models.LeaveRequest.objects.filter(tenant=t)
                .select_related('employee', 'leave_type').order_by('-created_at')[:6],
            'expiring_cert_rows': models.EmployeeCertification.objects.filter(
                tenant=t, expires_at__lte=soon,
            ).select_related('employee', 'certification').order_by('expires_at')[:6],
            'attendance_chart': att_chart,
            'cost_center_chart': cc_chart,
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 11.1  Departments
# ============================================================================

class DepartmentListView(TenantRequiredMixin, View):
    template_name = 'labor/departments/list.html'

    def get(self, request):
        qs = models.Department.objects.filter(tenant=request.tenant).select_related('parent', 'manager')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        active = request.GET.get('active', '')
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return render(request, self.template_name, {'page': _paginate(qs, request)})


class DepartmentCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/departments/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.DepartmentForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.DepartmentForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Department "{obj.name}" created.')
            return redirect('labor:department_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class DepartmentEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/departments/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.Department, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.DepartmentForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.Department, pk=pk, tenant=request.tenant)
        form = forms.DepartmentForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Department updated.')
            return redirect('labor:department_list')
        return render(request, self.template_name, {
            'form': form, 'mode': 'edit', 'obj': obj,
        })


class DepartmentDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Department, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Department deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - other records reference this department.')
        return redirect('labor:department_list')


# ============================================================================
# 11.1  Positions
# ============================================================================

class PositionListView(TenantRequiredMixin, View):
    template_name = 'labor/positions/list.html'

    def get(self, request):
        qs = models.Position.objects.filter(tenant=request.tenant).select_related('department')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(code__icontains=q))
        dept = request.GET.get('department', '')
        if dept:
            qs = qs.filter(department_id=dept)
        ctx = {
            'page': _paginate(qs, request),
            'departments': models.Department.objects.filter(tenant=request.tenant, is_active=True),
        }
        return render(request, self.template_name, ctx)


class PositionCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/positions/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.PositionForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.PositionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Position "{obj.title}" created.')
            return redirect('labor:position_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class PositionEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/positions/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.Position, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.PositionForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.Position, pk=pk, tenant=request.tenant)
        form = forms.PositionForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Position updated.')
            return redirect('labor:position_list')
        return render(request, self.template_name, {
            'form': form, 'mode': 'edit', 'obj': obj,
        })


class PositionDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Position, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Position deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - other records reference this position.')
        return redirect('labor:position_list')


# ============================================================================
# 11.1  Employees
# ============================================================================

class EmployeeListView(TenantRequiredMixin, View):
    template_name = 'labor/employees/list.html'

    def get(self, request):
        qs = models.Employee.objects.filter(tenant=request.tenant).select_related(
            'department', 'position',
        )
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(employee_number__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
            )
        dept = request.GET.get('department', '')
        if dept:
            qs = qs.filter(department_id=dept)
        pos = request.GET.get('position', '')
        if pos:
            qs = qs.filter(position_id=pos)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        ctx = {
            'page': _paginate(qs, request),
            'departments': models.Department.objects.filter(tenant=request.tenant, is_active=True),
            'positions': models.Position.objects.filter(tenant=request.tenant, is_active=True),
            'status_choices': models.Employee.STATUS_CHOICES,
        }
        return render(request, self.template_name, ctx)


class EmployeeCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/employees/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.EmployeeForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.EmployeeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Employee {obj.employee_number} created.')
            return redirect('labor:employee_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class EmployeeDetailView(TenantRequiredMixin, View):
    template_name = 'labor/employees/detail.html'

    def get(self, request, pk):
        emp = get_object_or_404(
            models.Employee.objects.select_related('department', 'position', 'user'),
            pk=pk, tenant=request.tenant,
        )
        ctx = {
            'obj': emp,
            'skills': emp.skills.select_related('skill').all(),
            'certs': emp.certifications.select_related('certification').all(),
            'documents': emp.documents.all().order_by('-created_at'),
            'recent_attendance': emp.attendance_records.order_by('-work_date')[:14],
            'recent_leaves': emp.leave_requests.select_related('leave_type').order_by('-created_at')[:6],
            'training_plans': emp.training_plans.select_related('program').order_by('-target_completion_date')[:6],
            'recent_bookings': emp.labor_bookings.select_related('cost_center').order_by('-worked_at')[:10],
        }
        return render(request, self.template_name, ctx)


class EmployeeEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/employees/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.EmployeeForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        form = forms.EmployeeForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Employee updated.')
            return redirect('labor:employee_detail', pk=obj.pk)
        return render(request, self.template_name, {
            'form': form, 'mode': 'edit', 'obj': obj,
        })


class EmployeeDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Employee deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - audit-trail records reference this employee.')
        return redirect('labor:employee_list')


class EmployeeTerminateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        ok = _atomic_status_transition(
            models.Employee, obj.pk, request.tenant,
            from_states=('active', 'on_leave', 'suspended'),
            to_state='terminated',
            extra_fields={'termination_date': timezone.now().date()},
        )
        if ok:
            messages.success(request, 'Employee terminated.')
        else:
            messages.error(request, 'Cannot terminate this employee in the current state.')
        return redirect('labor:employee_detail', pk=pk)


class EmployeeReactivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        ok = _atomic_status_transition(
            models.Employee, obj.pk, request.tenant,
            from_states=('on_leave', 'suspended', 'terminated'),
            to_state='active',
            extra_fields={'termination_date': None},
        )
        if ok:
            messages.success(request, 'Employee reactivated.')
        else:
            messages.error(request, 'Cannot reactivate from current state.')
        return redirect('labor:employee_detail', pk=pk)


# ============================================================================
# 11.1  Skills + Skills Matrix
# ============================================================================

class SkillListView(TenantRequiredMixin, View):
    template_name = 'labor/skills/list.html'

    def get(self, request):
        qs = models.Skill.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        cat = request.GET.get('category', '')
        if cat:
            qs = qs.filter(category=cat)
        ctx = {
            'page': _paginate(qs, request),
            'category_choices': models.Skill.CATEGORY_CHOICES,
        }
        return render(request, self.template_name, ctx)


class SkillCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/skills/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.SkillForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.SkillForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Skill "{obj.name}" created.')
            return redirect('labor:skill_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class SkillEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/skills/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.Skill, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.SkillForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.Skill, pk=pk, tenant=request.tenant)
        form = forms.SkillForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Skill updated.')
            return redirect('labor:skill_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class SkillDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Skill, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Skill deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - in use by an employee or assessment.')
        return redirect('labor:skill_list')


class SkillsMatrixView(TenantRequiredMixin, View):
    template_name = 'labor/skills_matrix/index.html'

    def get(self, request):
        t = request.tenant
        employees = list(
            models.Employee.objects.filter(tenant=t, status='active')
            .select_related('department', 'position').order_by('employee_number')
        )
        skills = list(models.Skill.objects.filter(tenant=t, is_active=True).order_by('code'))
        levels = {
            (es.employee_id, es.skill_id): es.proficiency
            for es in models.EmployeeSkill.objects.filter(tenant=t).only(
                'employee_id', 'skill_id', 'proficiency',
            )
        }
        rows = []
        for emp in employees:
            cells = [levels.get((emp.id, sk.id), 0) for sk in skills]
            rows.append({'employee': emp, 'cells': cells})
        return render(request, self.template_name, {
            'employees': employees, 'skills': skills, 'rows': rows,
        })


class EmployeeSkillCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/employee_skills/form.html'

    def get(self, request, pk):
        emp = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        form = forms.EmployeeSkillForm(tenant=request.tenant, employee=emp)
        return render(request, self.template_name, {'form': form, 'employee': emp})

    def post(self, request, pk):
        emp = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        form = forms.EmployeeSkillForm(request.POST, tenant=request.tenant, employee=emp)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.employee = emp
            obj.save()
            messages.success(request, 'Skill mapped.')
            return redirect('labor:employee_detail', pk=emp.pk)
        return render(request, self.template_name, {'form': form, 'employee': emp})


class EmployeeSkillDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.EmployeeSkill, pk=pk, tenant=request.tenant)
        emp_pk = obj.employee_id
        obj.delete()
        messages.success(request, 'Skill removed.')
        return redirect('labor:employee_detail', pk=emp_pk)


# ============================================================================
# 11.1  Certifications
# ============================================================================

class CertificationListView(TenantRequiredMixin, View):
    template_name = 'labor/certifications/list.html'

    def get(self, request):
        qs = models.Certification.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        return render(request, self.template_name, {'page': _paginate(qs, request)})


class CertificationCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/certifications/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.CertificationForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.CertificationForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Certification "{obj.name}" created.')
            return redirect('labor:certification_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class CertificationEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/certifications/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.Certification, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.CertificationForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.Certification, pk=pk, tenant=request.tenant)
        form = forms.CertificationForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Certification updated.')
            return redirect('labor:certification_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class CertificationDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Certification, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Certification deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - in use by employee records.')
        return redirect('labor:certification_list')


class EmployeeCertificationCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/employee_certifications/form.html'

    def get(self, request, pk):
        emp = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.EmployeeCertificationForm(tenant=request.tenant, employee=emp),
            'employee': emp,
        })

    def post(self, request, pk):
        emp = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        form = forms.EmployeeCertificationForm(
            request.POST, request.FILES, tenant=request.tenant, employee=emp,
        )
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.employee = emp
            obj.save()
            messages.success(request, 'Certification recorded.')
            return redirect('labor:employee_detail', pk=emp.pk)
        return render(request, self.template_name, {'form': form, 'employee': emp})


class EmployeeCertificationDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.EmployeeCertification, pk=pk, tenant=request.tenant)
        emp_pk = obj.employee_id
        obj.delete()
        messages.success(request, 'Certification removed.')
        return redirect('labor:employee_detail', pk=emp_pk)


class EmployeeDocumentCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/employee_documents/form.html'

    def get(self, request, pk):
        emp = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.EmployeeDocumentForm(tenant=request.tenant), 'employee': emp,
        })

    def post(self, request, pk):
        emp = get_object_or_404(models.Employee, pk=pk, tenant=request.tenant)
        form = forms.EmployeeDocumentForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.employee = emp
            obj.uploaded_by = request.user
            obj.save()
            messages.success(request, 'Document uploaded.')
            return redirect('labor:employee_detail', pk=emp.pk)
        return render(request, self.template_name, {'form': form, 'employee': emp})


class EmployeeDocumentDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.EmployeeDocument, pk=pk, tenant=request.tenant)
        emp_pk = obj.employee_id
        obj.delete()
        messages.success(request, 'Document removed.')
        return redirect('labor:employee_detail', pk=emp_pk)


# ============================================================================
# 11.2  Shifts
# ============================================================================

class ShiftListView(TenantRequiredMixin, View):
    template_name = 'labor/shifts/list.html'

    def get(self, request):
        qs = models.Shift.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        return render(request, self.template_name, {'page': _paginate(qs, request)})


class ShiftCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/shifts/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.ShiftForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.ShiftForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Shift "{obj.name}" created.')
            return redirect('labor:shift_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class ShiftEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/shifts/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.Shift, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.ShiftForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.Shift, pk=pk, tenant=request.tenant)
        form = forms.ShiftForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Shift updated.')
            return redirect('labor:shift_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class ShiftDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Shift, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Shift deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - in use by rosters or attendance.')
        return redirect('labor:shift_list')


# ============================================================================
# 11.2  Shift Rosters
# ============================================================================

class ShiftRosterListView(TenantRequiredMixin, View):
    template_name = 'labor/shift_rosters/list.html'

    def get(self, request):
        qs = models.ShiftRoster.objects.filter(tenant=request.tenant).select_related(
            'employee', 'shift',
        )
        emp = request.GET.get('employee', '')
        if emp:
            qs = qs.filter(employee_id=emp)
        sh = request.GET.get('shift', '')
        if sh:
            qs = qs.filter(shift_id=sh)
        ctx = {
            'page': _paginate(qs, request),
            'employees': models.Employee.objects.filter(tenant=request.tenant, status='active'),
            'shifts': models.Shift.objects.filter(tenant=request.tenant, is_active=True),
        }
        return render(request, self.template_name, ctx)


class ShiftRosterCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/shift_rosters/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.ShiftRosterForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.ShiftRosterForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Roster created.')
            return redirect('labor:roster_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class ShiftRosterEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/shift_rosters/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.ShiftRoster, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.ShiftRosterForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.ShiftRoster, pk=pk, tenant=request.tenant)
        form = forms.ShiftRosterForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Roster updated.')
            return redirect('labor:roster_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class ShiftRosterDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.ShiftRoster, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Roster removed.')
        return redirect('labor:roster_list')


# ============================================================================
# 11.2  Attendance Records
# ============================================================================

class AttendanceListView(TenantRequiredMixin, View):
    template_name = 'labor/attendance/list.html'

    def get(self, request):
        qs = models.AttendanceRecord.objects.filter(tenant=request.tenant).select_related(
            'employee', 'shift',
        )
        emp = request.GET.get('employee', '')
        if emp:
            qs = qs.filter(employee_id=emp)
        d = request.GET.get('work_date', '')
        if d:
            qs = qs.filter(work_date=d)
        status = request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        ctx = {
            'page': _paginate(qs, request),
            'employees': models.Employee.objects.filter(tenant=request.tenant),
            'status_choices': models.AttendanceRecord.STATUS_CHOICES,
        }
        return render(request, self.template_name, ctx)


class AttendanceCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/attendance/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.AttendanceRecordForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.AttendanceRecordForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            shift = obj.shift
            break_minutes = shift.break_minutes if shift else 0
            obj.worked_minutes = attendance_svc.compute_worked_minutes(
                obj.clock_in_at, obj.clock_out_at, break_minutes,
            )
            obj.save()
            messages.success(request, 'Attendance record saved.')
            return redirect('labor:attendance_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class AttendanceEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/attendance/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.AttendanceRecord, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.AttendanceRecordForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.AttendanceRecord, pk=pk, tenant=request.tenant)
        form = forms.AttendanceRecordForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            updated = form.save(commit=False)
            shift = updated.shift
            break_minutes = shift.break_minutes if shift else 0
            updated.worked_minutes = attendance_svc.compute_worked_minutes(
                updated.clock_in_at, updated.clock_out_at, break_minutes,
            )
            updated.save()
            messages.success(request, 'Attendance updated.')
            return redirect('labor:attendance_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class AttendanceDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.AttendanceRecord, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Attendance record deleted.')
        return redirect('labor:attendance_list')


# ============================================================================
# 11.2  Leave Types
# ============================================================================

class LeaveTypeListView(TenantRequiredMixin, View):
    template_name = 'labor/leave_types/list.html'

    def get(self, request):
        qs = models.LeaveType.objects.filter(tenant=request.tenant)
        return render(request, self.template_name, {'page': _paginate(qs, request)})


class LeaveTypeCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/leave_types/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.LeaveTypeForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.LeaveTypeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Leave type "{obj.name}" created.')
            return redirect('labor:leave_type_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class LeaveTypeEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/leave_types/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.LeaveType, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.LeaveTypeForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.LeaveType, pk=pk, tenant=request.tenant)
        form = forms.LeaveTypeForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Leave type updated.')
            return redirect('labor:leave_type_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class LeaveTypeDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.LeaveType, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Leave type deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - referenced by leave requests.')
        return redirect('labor:leave_type_list')


# ============================================================================
# 11.2  Leave Requests
# ============================================================================

class LeaveRequestListView(TenantRequiredMixin, View):
    template_name = 'labor/leave_requests/list.html'

    def get(self, request):
        qs = models.LeaveRequest.objects.filter(tenant=request.tenant).select_related(
            'employee', 'leave_type',
        )
        emp = request.GET.get('employee', '')
        if emp:
            qs = qs.filter(employee_id=emp)
        st = request.GET.get('status', '')
        if st:
            qs = qs.filter(status=st)
        ctx = {
            'page': _paginate(qs, request),
            'employees': models.Employee.objects.filter(tenant=request.tenant),
            'status_choices': models.LeaveRequest.STATUS_CHOICES,
        }
        return render(request, self.template_name, ctx)


class LeaveRequestCreateView(TenantRequiredMixin, View):
    template_name = 'labor/leave_requests/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.LeaveRequestForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.LeaveRequestForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Leave request {obj.request_number} created.')
            return redirect('labor:leave_request_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class LeaveRequestDetailView(TenantRequiredMixin, View):
    template_name = 'labor/leave_requests/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.LeaveRequest.objects.select_related('employee', 'leave_type', 'decided_by'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {'obj': obj})


class LeaveRequestEditView(TenantRequiredMixin, View):
    template_name = 'labor/leave_requests/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.LeaveRequest, pk=pk, tenant=request.tenant)
        if obj.status not in ('draft',):
            messages.error(request, 'Only draft leave requests can be edited.')
            return redirect('labor:leave_request_detail', pk=pk)
        return render(request, self.template_name, {
            'form': forms.LeaveRequestForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.LeaveRequest, pk=pk, tenant=request.tenant)
        if obj.status not in ('draft',):
            messages.error(request, 'Only draft leave requests can be edited.')
            return redirect('labor:leave_request_detail', pk=pk)
        form = forms.LeaveRequestForm(
            request.POST, request.FILES, instance=obj, tenant=request.tenant,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Leave request updated.')
            return redirect('labor:leave_request_detail', pk=pk)
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class LeaveRequestDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.LeaveRequest, pk=pk, tenant=request.tenant)
        if obj.status not in ('draft', 'cancelled', 'rejected'):
            messages.error(request, 'Only draft/cancelled/rejected leave requests can be deleted.')
            return redirect('labor:leave_request_detail', pk=pk)
        obj.delete()
        messages.success(request, 'Leave request deleted.')
        return redirect('labor:leave_request_list')


class LeaveRequestSubmitView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.LeaveRequest, pk, request.tenant,
            from_states=('draft',), to_state='submitted',
            extra_fields={'submitted_at': timezone.now()},
        )
        if ok:
            messages.success(request, 'Leave request submitted.')
        else:
            messages.error(request, 'Cannot submit from current state.')
        return redirect('labor:leave_request_detail', pk=pk)


class LeaveRequestApproveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.LeaveRequest, pk, request.tenant,
            from_states=('submitted',), to_state='approved',
            extra_fields={'decided_by': request.user, 'decided_at': timezone.now()},
        )
        if ok:
            messages.success(request, 'Leave request approved.')
        else:
            messages.error(request, 'Cannot approve from current state.')
        return redirect('labor:leave_request_detail', pk=pk)


class LeaveRequestRejectView(TenantAdminRequiredMixin, View):
    template_name = 'labor/leave_requests/decision.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.LeaveRequest, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.LeaveDecisionForm(mode='reject'), 'mode': 'reject', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.LeaveRequest, pk=pk, tenant=request.tenant)
        form = forms.LeaveDecisionForm(request.POST, mode='reject')
        if form.is_valid():
            ok = _atomic_status_transition(
                models.LeaveRequest, pk, request.tenant,
                from_states=('submitted',), to_state='rejected',
                extra_fields={
                    'decided_by': request.user,
                    'decided_at': timezone.now(),
                    'decision_notes': form.cleaned_data['decision_notes'],
                },
            )
            if ok:
                messages.success(request, 'Leave request rejected.')
                return redirect('labor:leave_request_detail', pk=pk)
            messages.error(request, 'Cannot reject from current state.')
        return render(request, self.template_name, {
            'form': form, 'mode': 'reject', 'obj': obj,
        })


class LeaveRequestCancelView(TenantRequiredMixin, View):
    template_name = 'labor/leave_requests/decision.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.LeaveRequest, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.LeaveDecisionForm(
                mode='cancel', was_approved=(obj.status == 'approved'),
            ),
            'mode': 'cancel', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.LeaveRequest, pk=pk, tenant=request.tenant)
        form = forms.LeaveDecisionForm(
            request.POST, mode='cancel',
            was_approved=(obj.status == 'approved'),
        )
        if form.is_valid():
            ok = _atomic_status_transition(
                models.LeaveRequest, pk, request.tenant,
                from_states=('draft', 'submitted', 'approved'),
                to_state='cancelled',
                extra_fields={
                    'decided_by': request.user,
                    'decided_at': timezone.now(),
                    'decision_notes': form.cleaned_data['decision_notes'],
                },
            )
            if ok:
                messages.success(request, 'Leave request cancelled.')
                return redirect('labor:leave_request_detail', pk=pk)
            messages.error(request, 'Cannot cancel from current state.')
        return render(request, self.template_name, {
            'form': form, 'mode': 'cancel', 'obj': obj,
        })


# ============================================================================
# 11.2  Holidays
# ============================================================================

class HolidayListView(TenantRequiredMixin, View):
    template_name = 'labor/holidays/list.html'

    def get(self, request):
        qs = models.Holiday.objects.filter(tenant=request.tenant)
        year = request.GET.get('year', '')
        if year and year.isdigit():
            qs = qs.filter(holiday_date__year=int(year))
        return render(request, self.template_name, {'page': _paginate(qs, request)})


class HolidayCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/holidays/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.HolidayForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.HolidayForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Holiday added.')
            return redirect('labor:holiday_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class HolidayEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/holidays/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.Holiday, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.HolidayForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.Holiday, pk=pk, tenant=request.tenant)
        form = forms.HolidayForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Holiday updated.')
            return redirect('labor:holiday_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class HolidayDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Holiday, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Holiday removed.')
        return redirect('labor:holiday_list')


# ============================================================================
# 11.3  Cost Centers
# ============================================================================

class CostCenterListView(TenantRequiredMixin, View):
    template_name = 'labor/cost_centers/list.html'

    def get(self, request):
        qs = models.CostCenter.objects.filter(tenant=request.tenant).select_related('parent')
        cc_type = request.GET.get('cc_type', '')
        if cc_type:
            qs = qs.filter(cc_type=cc_type)
        ctx = {
            'page': _paginate(qs, request),
            'cc_type_choices': models.CostCenter.CC_TYPE_CHOICES,
        }
        return render(request, self.template_name, ctx)


class CostCenterCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/cost_centers/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.CostCenterForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.CostCenterForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Cost center "{obj.name}" created.')
            return redirect('labor:cost_center_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class CostCenterEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/cost_centers/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.CostCenter, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.CostCenterForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.CostCenter, pk=pk, tenant=request.tenant)
        form = forms.CostCenterForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cost center updated.')
            return redirect('labor:cost_center_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class CostCenterDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.CostCenter, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Cost center deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - referenced by bookings or assets.')
        return redirect('labor:cost_center_list')


# ============================================================================
# 11.3  Labor Rates
# ============================================================================

class LaborRateListView(TenantRequiredMixin, View):
    template_name = 'labor/labor_rates/list.html'

    def get(self, request):
        qs = models.LaborRate.objects.filter(tenant=request.tenant).select_related('employee')
        emp = request.GET.get('employee', '')
        if emp:
            qs = qs.filter(employee_id=emp)
        ctx = {
            'page': _paginate(qs, request),
            'employees': models.Employee.objects.filter(tenant=request.tenant),
        }
        return render(request, self.template_name, ctx)


class LaborRateCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/labor_rates/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.LaborRateForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.LaborRateForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Labor rate added.')
            return redirect('labor:labor_rate_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class LaborRateEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/labor_rates/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.LaborRate, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.LaborRateForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.LaborRate, pk=pk, tenant=request.tenant)
        form = forms.LaborRateForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Labor rate updated.')
            return redirect('labor:labor_rate_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class LaborRateDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.LaborRate, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Labor rate removed.')
        return redirect('labor:labor_rate_list')


# ============================================================================
# 11.3  Labor Bookings
# ============================================================================

class LaborBookingListView(TenantRequiredMixin, View):
    template_name = 'labor/labor_bookings/list.html'

    def get(self, request):
        qs = models.LaborBooking.objects.filter(tenant=request.tenant).select_related(
            'employee', 'cost_center',
        )
        emp = request.GET.get('employee', '')
        if emp:
            qs = qs.filter(employee_id=emp)
        cc = request.GET.get('cost_center', '')
        if cc:
            qs = qs.filter(cost_center_id=cc)
        kind = request.GET.get('kind', '')
        if kind:
            qs = qs.filter(kind=kind)
        source = request.GET.get('source_type', '')
        if source:
            qs = qs.filter(source_type=source)
        ctx = {
            'page': _paginate(qs, request),
            'employees': models.Employee.objects.filter(tenant=request.tenant),
            'cost_centers': models.CostCenter.objects.filter(tenant=request.tenant, is_active=True),
            'kind_choices': models.LaborBooking.KIND_CHOICES,
            'source_choices': models.LaborBooking.SOURCE_TYPE_CHOICES,
        }
        return render(request, self.template_name, ctx)


class LaborBookingDetailView(TenantRequiredMixin, View):
    template_name = 'labor/labor_bookings/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.LaborBooking.objects.select_related('employee', 'cost_center'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, self.template_name, {'obj': obj})


class LaborBookingCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/labor_bookings/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.LaborBookingForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.LaborBookingForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.source_type = 'manual'
            obj.save()
            messages.success(request, f'Labor booking {obj.booking_number} created.')
            return redirect('labor:labor_booking_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class LaborBookingDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.LaborBooking, pk=pk, tenant=request.tenant)
        if obj.source_type != 'manual':
            messages.error(request, 'Only manually created bookings can be deleted.')
            return redirect('labor:labor_booking_detail', pk=pk)
        obj.delete()
        messages.success(request, 'Labor booking deleted.')
        return redirect('labor:labor_booking_list')


class LaborBookingSummaryView(TenantRequiredMixin, View):
    template_name = 'labor/labor_bookings/summary.html'

    def get(self, request):
        t = request.tenant
        today = timezone.now().date()
        start = request.GET.get('start') or (today - timedelta(days=30)).isoformat()
        end = request.GET.get('end') or today.isoformat()
        try:
            start_d = date.fromisoformat(start)
            end_d = date.fromisoformat(end)
        except ValueError:
            start_d, end_d = today - timedelta(days=30), today
        bookings = models.LaborBooking.objects.filter(
            tenant=t, worked_at__date__gte=start_d, worked_at__date__lte=end_d,
        ).select_related('cost_center')
        rows = (
            bookings.values('cost_center__id', 'cost_center__name', 'cost_center__code', 'kind')
            .annotate(total_minutes=Sum('minutes'), total_cost=Sum('total_cost'))
            .order_by('cost_center__code', 'kind')
        )
        grand_minutes = sum(r['total_minutes'] or 0 for r in rows)
        grand_cost = sum(r['total_cost'] or Decimal('0') for r in rows)
        ctx = {
            'rows': list(rows), 'start': start_d, 'end': end_d,
            'grand_minutes': grand_minutes, 'grand_cost': grand_cost,
        }
        return render(request, self.template_name, ctx)


# ============================================================================
# 11.4  Training Programs
# ============================================================================

class TrainingProgramListView(TenantRequiredMixin, View):
    template_name = 'labor/training_programs/list.html'

    def get(self, request):
        qs = models.TrainingProgram.objects.filter(tenant=request.tenant).select_related('competency_target')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        mode = request.GET.get('delivery_mode', '')
        if mode:
            qs = qs.filter(delivery_mode=mode)
        ctx = {
            'page': _paginate(qs, request),
            'mode_choices': models.TrainingProgram.DELIVERY_MODE_CHOICES,
        }
        return render(request, self.template_name, ctx)


class TrainingProgramCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/training_programs/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.TrainingProgramForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.TrainingProgramForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Program "{obj.name}" created.')
            return redirect('labor:program_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class TrainingProgramEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/training_programs/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.TrainingProgram, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.TrainingProgramForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.TrainingProgram, pk=pk, tenant=request.tenant)
        form = forms.TrainingProgramForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Program updated.')
            return redirect('labor:program_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class TrainingProgramDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.TrainingProgram, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Program deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - has plans or sessions.')
        return redirect('labor:program_list')


# ============================================================================
# 11.4  Training Plans
# ============================================================================

class TrainingPlanListView(TenantRequiredMixin, View):
    template_name = 'labor/training_plans/list.html'

    def get(self, request):
        qs = models.TrainingPlan.objects.filter(tenant=request.tenant).select_related(
            'employee', 'program',
        )
        emp = request.GET.get('employee', '')
        if emp:
            qs = qs.filter(employee_id=emp)
        st = request.GET.get('status', '')
        if st:
            qs = qs.filter(status=st)
        ctx = {
            'page': _paginate(qs, request),
            'employees': models.Employee.objects.filter(tenant=request.tenant),
            'status_choices': models.TrainingPlan.STATUS_CHOICES,
        }
        return render(request, self.template_name, ctx)


class TrainingPlanCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/training_plans/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.TrainingPlanForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.TrainingPlanForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.assigned_by = request.user
            obj.save()
            messages.success(request, 'Plan created.')
            return redirect('labor:plan_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class TrainingPlanEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/training_plans/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.TrainingPlan, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.TrainingPlanForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.TrainingPlan, pk=pk, tenant=request.tenant)
        form = forms.TrainingPlanForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Plan updated.')
            return redirect('labor:plan_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class TrainingPlanDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.TrainingPlan, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Plan removed.')
        return redirect('labor:plan_list')


class TrainingPlanStartView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.TrainingPlan, pk, request.tenant,
            from_states=('assigned',), to_state='in_progress',
        )
        messages.success(request, 'Plan started.') if ok else messages.error(request, 'Cannot start.')
        return redirect('labor:plan_list')


class TrainingPlanCompleteView(TenantRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.TrainingPlan, pk, request.tenant,
            from_states=('assigned', 'in_progress'), to_state='completed',
        )
        messages.success(request, 'Plan completed.') if ok else messages.error(request, 'Cannot complete.')
        return redirect('labor:plan_list')


class TrainingPlanWaiveView(TenantAdminRequiredMixin, View):
    template_name = 'labor/training_plans/waive.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.TrainingPlan, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.TrainingPlanWaiveForm(), 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.TrainingPlan, pk=pk, tenant=request.tenant)
        form = forms.TrainingPlanWaiveForm(request.POST)
        if form.is_valid():
            ok = _atomic_status_transition(
                models.TrainingPlan, pk, request.tenant,
                from_states=('assigned', 'in_progress', 'overdue'),
                to_state='waived',
                extra_fields={'notes': form.cleaned_data['notes']},
            )
            if ok:
                messages.success(request, 'Plan waived.')
                return redirect('labor:plan_list')
            messages.error(request, 'Cannot waive from current state.')
        return render(request, self.template_name, {'form': form, 'obj': obj})


# ============================================================================
# 11.4  Training Sessions
# ============================================================================

class TrainingSessionListView(TenantRequiredMixin, View):
    template_name = 'labor/training_sessions/list.html'

    def get(self, request):
        qs = models.TrainingSession.objects.filter(tenant=request.tenant).select_related(
            'program', 'instructor',
        )
        st = request.GET.get('status', '')
        if st:
            qs = qs.filter(status=st)
        ctx = {
            'page': _paginate(qs, request),
            'status_choices': models.TrainingSession.STATUS_CHOICES,
        }
        return render(request, self.template_name, ctx)


class TrainingSessionCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/training_sessions/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.TrainingSessionForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.TrainingSessionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Session {obj.session_number} created.')
            return redirect('labor:session_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class TrainingSessionDetailView(TenantRequiredMixin, View):
    template_name = 'labor/training_sessions/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.TrainingSession.objects.select_related('program', 'instructor'),
            pk=pk, tenant=request.tenant,
        )
        attendees = obj.attendees.select_related('employee').order_by('employee__employee_number')
        return render(request, self.template_name, {'obj': obj, 'attendees': attendees})


class TrainingSessionEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/training_sessions/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.TrainingSession, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.TrainingSessionForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.TrainingSession, pk=pk, tenant=request.tenant)
        form = forms.TrainingSessionForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Session updated.')
            return redirect('labor:session_detail', pk=pk)
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class TrainingSessionDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.TrainingSession, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Session deleted.')
        return redirect('labor:session_list')


class TrainingAttendanceCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/training_attendance/form.html'

    def get(self, request, pk):
        session = get_object_or_404(models.TrainingSession, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.TrainingAttendanceForm(tenant=request.tenant, session=session),
            'session': session,
        })

    def post(self, request, pk):
        session = get_object_or_404(models.TrainingSession, pk=pk, tenant=request.tenant)
        form = forms.TrainingAttendanceForm(
            request.POST, tenant=request.tenant, session=session,
        )
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.session = session
            obj.recorded_by = request.user
            obj.save()
            messages.success(request, 'Attendance recorded.')
            return redirect('labor:session_detail', pk=session.pk)
        return render(request, self.template_name, {'form': form, 'session': session})


class TrainingAttendanceDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.TrainingAttendance, pk=pk, tenant=request.tenant)
        sess_pk = obj.session_id
        obj.delete()
        messages.success(request, 'Attendance removed.')
        return redirect('labor:session_detail', pk=sess_pk)


# ============================================================================
# 11.4  Competency Assessments
# ============================================================================

class AssessmentListView(TenantRequiredMixin, View):
    template_name = 'labor/competency_assessments/list.html'

    def get(self, request):
        qs = models.CompetencyAssessment.objects.filter(tenant=request.tenant).select_related(
            'employee', 'position',
        )
        emp = request.GET.get('employee', '')
        if emp:
            qs = qs.filter(employee_id=emp)
        st = request.GET.get('status', '')
        if st:
            qs = qs.filter(status=st)
        ctx = {
            'page': _paginate(qs, request),
            'employees': models.Employee.objects.filter(tenant=request.tenant),
            'status_choices': models.CompetencyAssessment.STATUS_CHOICES,
        }
        return render(request, self.template_name, ctx)


class AssessmentCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/competency_assessments/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.CompetencyAssessmentForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.CompetencyAssessmentForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.assessor = request.user
            obj.save()
            messages.success(request, f'Assessment {obj.assessment_number} created.')
            return redirect('labor:assessment_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class AssessmentDetailView(TenantRequiredMixin, View):
    template_name = 'labor/competency_assessments/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.CompetencyAssessment.objects.select_related('employee', 'position'),
            pk=pk, tenant=request.tenant,
        )
        results = obj.results.select_related('skill').order_by('skill__code')
        ctx = {
            'obj': obj, 'results': results,
            'gap_summary': competency_svc.gap_summary(results),
            'overall': competency_svc.compute_overall_score(results),
            'result_form': forms.CompetencyResultForm(tenant=request.tenant, assessment=obj),
        }
        return render(request, self.template_name, ctx)


class AssessmentEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/competency_assessments/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.CompetencyAssessment, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.CompetencyAssessmentForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.CompetencyAssessment, pk=pk, tenant=request.tenant)
        form = forms.CompetencyAssessmentForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Assessment updated.')
            return redirect('labor:assessment_detail', pk=pk)
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class AssessmentDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.CompetencyAssessment, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, 'Assessment deleted.')
        return redirect('labor:assessment_list')


class AssessmentCompleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.CompetencyAssessment, pk=pk, tenant=request.tenant)
        results = list(obj.results.all())
        form = forms.CompetencyAssessmentCompleteForm(
            request.POST, has_results=bool(results),
        )
        if not form.is_valid():
            for err in form.non_field_errors():
                messages.error(request, err)
            return redirect('labor:assessment_detail', pk=pk)
        score = competency_svc.compute_overall_score(results)
        ok = _atomic_status_transition(
            models.CompetencyAssessment, pk, request.tenant,
            from_states=('draft',), to_state='completed',
            extra_fields={'overall_score': score},
        )
        if ok:
            messages.success(request, f'Assessment completed (score: {score}).')
        else:
            messages.error(request, 'Cannot complete from current state.')
        return redirect('labor:assessment_detail', pk=pk)


class CompetencyResultCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.CompetencyAssessment, pk=pk, tenant=request.tenant)
        if obj.status != 'draft':
            messages.error(request, 'Cannot edit results on a completed assessment.')
            return redirect('labor:assessment_detail', pk=pk)
        form = forms.CompetencyResultForm(
            request.POST, tenant=request.tenant, assessment=obj,
        )
        if form.is_valid():
            r = form.save(commit=False)
            r.tenant = request.tenant
            r.assessment = obj
            r.save()
            messages.success(request, 'Result added.')
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f'{field}: {err}')
        return redirect('labor:assessment_detail', pk=pk)


class CompetencyResultDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.CompetencyResult, pk=pk, tenant=request.tenant)
        ass_pk = obj.assessment_id
        if obj.assessment.status != 'draft':
            messages.error(request, 'Cannot delete results on a completed assessment.')
        else:
            obj.delete()
            messages.success(request, 'Result removed.')
        return redirect('labor:assessment_detail', pk=ass_pk)


# ============================================================================
# 11.5  Incentive Schemes
# ============================================================================

class SchemeListView(TenantRequiredMixin, View):
    template_name = 'labor/incentive_schemes/list.html'

    def get(self, request):
        qs = models.IncentiveScheme.objects.filter(tenant=request.tenant)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        st = request.GET.get('scheme_type', '')
        if st:
            qs = qs.filter(scheme_type=st)
        ctx = {
            'page': _paginate(qs, request),
            'type_choices': models.IncentiveScheme.SCHEME_TYPE_CHOICES,
        }
        return render(request, self.template_name, ctx)


class SchemeCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/incentive_schemes/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.IncentiveSchemeForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.IncentiveSchemeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Scheme "{obj.name}" created.')
            return redirect('labor:scheme_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class SchemeDetailView(TenantRequiredMixin, View):
    template_name = 'labor/incentive_schemes/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.IncentiveScheme.objects, pk=pk, tenant=request.tenant,
        )
        rates = obj.piece_rates.select_related('product', 'operation')
        ctx = {
            'obj': obj, 'rates': rates,
            'rate_form': forms.PieceRateForm(tenant=request.tenant, scheme=obj),
        }
        return render(request, self.template_name, ctx)


class SchemeEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/incentive_schemes/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.IncentiveScheme, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.IncentiveSchemeForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.IncentiveScheme, pk=pk, tenant=request.tenant)
        form = forms.IncentiveSchemeForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Scheme updated.')
            return redirect('labor:scheme_detail', pk=pk)
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class SchemeDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.IncentiveScheme, pk=pk, tenant=request.tenant)
        try:
            obj.delete()
            messages.success(request, 'Scheme deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - has runs or rates.')
        return redirect('labor:scheme_list')


class PieceRateCreateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        scheme = get_object_or_404(models.IncentiveScheme, pk=pk, tenant=request.tenant)
        form = forms.PieceRateForm(request.POST, tenant=request.tenant, scheme=scheme)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.scheme = scheme
            obj.save()
            messages.success(request, 'Piece rate added.')
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f'{field}: {err}')
        return redirect('labor:scheme_detail', pk=pk)


class PieceRateDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.PieceRate, pk=pk, tenant=request.tenant)
        scheme_pk = obj.scheme_id
        obj.delete()
        messages.success(request, 'Piece rate removed.')
        return redirect('labor:scheme_detail', pk=scheme_pk)


# ============================================================================
# 11.5  Incentive Periods
# ============================================================================

class PeriodListView(TenantRequiredMixin, View):
    template_name = 'labor/incentive_periods/list.html'

    def get(self, request):
        qs = models.IncentivePeriod.objects.filter(tenant=request.tenant)
        st = request.GET.get('status', '')
        if st:
            qs = qs.filter(status=st)
        ctx = {
            'page': _paginate(qs, request),
            'status_choices': models.IncentivePeriod.STATUS_CHOICES,
        }
        return render(request, self.template_name, ctx)


class PeriodCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/incentive_periods/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.IncentivePeriodForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.IncentivePeriodForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, 'Period created.')
            return redirect('labor:period_list')
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class PeriodEditView(TenantAdminRequiredMixin, View):
    template_name = 'labor/incentive_periods/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.IncentivePeriod, pk=pk, tenant=request.tenant)
        if obj.status != 'open':
            messages.error(request, 'Only open periods are editable.')
            return redirect('labor:period_list')
        return render(request, self.template_name, {
            'form': forms.IncentivePeriodForm(instance=obj, tenant=request.tenant),
            'mode': 'edit', 'obj': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.IncentivePeriod, pk=pk, tenant=request.tenant)
        if obj.status != 'open':
            messages.error(request, 'Only open periods are editable.')
            return redirect('labor:period_list')
        form = forms.IncentivePeriodForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Period updated.')
            return redirect('labor:period_list')
        return render(request, self.template_name, {'form': form, 'mode': 'edit', 'obj': obj})


class PeriodLockView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.IncentivePeriod, pk, request.tenant,
            from_states=('open',), to_state='locked',
        )
        messages.success(request, 'Period locked.') if ok else messages.error(request, 'Cannot lock.')
        return redirect('labor:period_list')


class PeriodPayView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.IncentivePeriod, pk, request.tenant,
            from_states=('locked',), to_state='paid',
        )
        messages.success(request, 'Period marked paid.') if ok else messages.error(request, 'Cannot mark paid.')
        return redirect('labor:period_list')


class PeriodDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.IncentivePeriod, pk=pk, tenant=request.tenant)
        if obj.status != 'open':
            messages.error(request, 'Only open periods can be deleted.')
            return redirect('labor:period_list')
        try:
            obj.delete()
            messages.success(request, 'Period deleted.')
        except IntegrityError:
            messages.error(request, 'Cannot delete - referenced by runs.')
        return redirect('labor:period_list')


# ============================================================================
# 11.5  Incentive Runs
# ============================================================================

class RunListView(TenantRequiredMixin, View):
    template_name = 'labor/incentive_runs/list.html'

    def get(self, request):
        qs = models.IncentiveRun.objects.filter(tenant=request.tenant).select_related(
            'period', 'scheme',
        )
        st = request.GET.get('status', '')
        if st:
            qs = qs.filter(status=st)
        ctx = {
            'page': _paginate(qs, request),
            'status_choices': models.IncentiveRun.STATUS_CHOICES,
        }
        return render(request, self.template_name, ctx)


class RunCreateView(TenantAdminRequiredMixin, View):
    template_name = 'labor/incentive_runs/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.IncentiveRunForm(tenant=request.tenant), 'mode': 'create',
        })

    def post(self, request):
        form = forms.IncentiveRunForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Run {obj.run_number} created.')
            return redirect('labor:run_detail', pk=obj.pk)
        return render(request, self.template_name, {'form': form, 'mode': 'create'})


class RunDetailView(TenantRequiredMixin, View):
    template_name = 'labor/incentive_runs/detail.html'

    def get(self, request, pk):
        obj = get_object_or_404(
            models.IncentiveRun.objects.select_related('period', 'scheme'),
            pk=pk, tenant=request.tenant,
        )
        lines = obj.lines.select_related('employee').order_by('employee__employee_number')
        return render(request, self.template_name, {'obj': obj, 'lines': lines})


class RunRunView(TenantAdminRequiredMixin, View):
    """Execute the calculation: scan ProductionReport in the period, group by employee, accumulate lines."""

    def post(self, request, pk):
        run = get_object_or_404(models.IncentiveRun, pk=pk, tenant=request.tenant)
        if run.status != 'draft':
            messages.error(request, 'Only draft runs can be executed.')
            return redirect('labor:run_detail', pk=pk)
        if run.period.status != 'open':
            messages.error(request, 'The period must be open to run a calculation.')
            return redirect('labor:run_detail', pk=pk)
        scheme = run.scheme
        period = run.period
        # Lazy import to avoid circular imports.
        from apps.mes.models import ProductionReport
        reports = ProductionReport.all_objects.filter(
            tenant=request.tenant,
            reported_at__date__gte=period.start_date,
            reported_at__date__lte=period.end_date,
            good_qty__gt=0,
        ).select_related('work_order_operation', 'work_order_operation__work_order',
                         'work_order_operation__work_order__production_order',
                         'reported_by')
        product_filter = list(scheme.applicable_products.values_list('pk', flat=True)) \
            if scheme.applicable_products.exists() else None
        with transaction.atomic():
            run.status = 'running'
            run.started_at = timezone.now()
            run.save(update_fields=['status', 'started_at', 'updated_at'])
            run.lines.all().delete()  # idempotent rerun
            grand = Decimal('0')
            line_cache: dict = {}
            piece_rates = list(scheme.piece_rates.all())
            for r in reports:
                user = r.reported_by
                if user is None:
                    continue
                employee = models.Employee.all_objects.filter(
                    tenant_id=request.tenant.id, user_id=user.id,
                ).first()
                if employee is None:
                    continue
                op = r.work_order_operation
                product = None
                operation = None
                try:
                    product = op.work_order.production_order.product
                    operation = op.routing_operation
                except AttributeError:
                    pass
                if product_filter and product and product.pk not in product_filter:
                    continue
                rate_row = piece_rate_svc.select_rate(
                    piece_rates, product=product, operation=operation, qty=r.good_qty,
                )
                if rate_row is None:
                    continue
                key = employee.pk
                if key not in line_cache:
                    line_cache[key] = {
                        'employee': employee, 'units': Decimal('0'),
                        'rate': rate_row.rate_per_unit, 'reports': [],
                    }
                line_cache[key]['units'] += Decimal(r.good_qty)
                line_cache[key]['reports'].append(r)
            for key, agg in line_cache.items():
                amount = piece_rate_svc.compute_amount(agg['units'], agg['rate'])
                line = models.IncentiveLine.objects.create(
                    tenant=request.tenant, run=run,
                    employee=agg['employee'],
                    qualifying_units=agg['units'],
                    rate_applied=agg['rate'],
                    amount=amount,
                )
                if agg['reports']:
                    line.production_reports.add(*agg['reports'])
                grand += amount
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.total_amount = grand
            run.save(update_fields=['status', 'completed_at', 'total_amount', 'updated_at'])
        messages.success(request, f'Run completed - total {grand}.')
        return redirect('labor:run_detail', pk=pk)


class RunDiscardView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        run = get_object_or_404(models.IncentiveRun, pk=pk, tenant=request.tenant)
        if run.status not in ('draft', 'completed'):
            messages.error(request, 'Cannot discard from current state.')
            return redirect('labor:run_detail', pk=pk)
        with transaction.atomic():
            run.lines.all().delete()
            run.status = 'discarded'
            run.total_amount = Decimal('0')
            run.save(update_fields=['status', 'total_amount', 'updated_at'])
        messages.success(request, 'Run discarded.')
        return redirect('labor:run_detail', pk=pk)


class RunDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.IncentiveRun, pk=pk, tenant=request.tenant)
        if obj.status not in ('draft', 'discarded'):
            messages.error(request, 'Only draft/discarded runs can be deleted.')
            return redirect('labor:run_detail', pk=pk)
        obj.delete()
        messages.success(request, 'Run deleted.')
        return redirect('labor:run_list')
