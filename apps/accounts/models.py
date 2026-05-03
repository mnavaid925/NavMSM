"""Custom User, UserProfile (theme prefs), UserInvite."""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.core.models import Tenant, TenantAwareModel, TimeStampedModel


class User(AbstractUser):
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('tenant_admin', 'Tenant Admin'),
        ('production_manager', 'Production Manager'),
        ('plant_manager', 'Plant Manager'),
        ('supervisor', 'Supervisor'),
        ('operator', 'Operator'),
        ('quality_inspector', 'Quality Inspector'),
        ('warehouse_staff', 'Warehouse Staff'),
        ('procurement', 'Procurement'),
        ('accountant', 'Accountant'),
        ('viewer', 'Viewer'),
        ('supplier', 'Supplier (External)'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True,
    )
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='operator')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    is_tenant_admin = models.BooleanField(default=False)
    # Module 9 - Procurement: Supplier-portal users carry a FK to their supplier
    # company so views can scope POs/ASNs/Invoices to their own org.
    supplier_company = models.ForeignKey(
        'procurement.Supplier',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='portal_users',
        help_text="Set only when role='supplier'.",
    )

    class Meta:
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return self.get_full_name() or self.username

    def get_initials(self):
        if self.first_name and self.last_name:
            return f'{self.first_name[0]}{self.last_name[0]}'.upper()
        return (self.username[:2] or 'U').upper()


class UserProfile(TimeStampedModel):
    THEME_CHOICES = [('light', 'Light'), ('dark', 'Dark')]
    LAYOUT_CHOICES = [
        ('vertical', 'Vertical'),
        ('horizontal', 'Horizontal'),
        ('detached', 'Detached'),
    ]
    SIDEBAR_SIZE_CHOICES = [
        ('default', 'Default'),
        ('compact', 'Compact'),
        ('small', 'Small Icon'),
        ('hover', 'Icon Hover'),
    ]
    SIDEBAR_COLOR_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('brand', 'Brand'),
    ]
    LAYOUT_WIDTH_CHOICES = [('fluid', 'Fluid'), ('boxed', 'Boxed')]
    LAYOUT_POSITION_CHOICES = [('fixed', 'Fixed'), ('scrollable', 'Scrollable')]
    DIRECTION_CHOICES = [('ltr', 'LTR'), ('rtl', 'RTL')]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)

    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='light')
    layout = models.CharField(max_length=20, choices=LAYOUT_CHOICES, default='vertical')
    sidebar_color = models.CharField(max_length=20, choices=SIDEBAR_COLOR_CHOICES, default='light')
    sidebar_size = models.CharField(max_length=20, choices=SIDEBAR_SIZE_CHOICES, default='default')
    topbar_color = models.CharField(max_length=20, default='light')
    layout_width = models.CharField(max_length=20, choices=LAYOUT_WIDTH_CHOICES, default='fluid')
    layout_position = models.CharField(max_length=20, choices=LAYOUT_POSITION_CHOICES, default='fixed')
    direction = models.CharField(max_length=5, choices=DIRECTION_CHOICES, default='ltr')

    def __str__(self):
        return f'Profile of {self.user}'


class UserInvite(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    email = models.EmailField()
    role = models.CharField(max_length=30, choices=User.ROLE_CHOICES, default='operator')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invites')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Invite to {self.email} ({self.status})'
