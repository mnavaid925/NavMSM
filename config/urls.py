from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.core.views import DashboardView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', DashboardView.as_view(), name='dashboard'),
    path('accounts/', include('apps.accounts.urls')),
    path('tenants/', include('apps.tenants.urls')),
    path('plm/', include('apps.plm.urls')),
    path('bom/', include('apps.bom.urls')),
    path('pps/', include('apps.pps.urls')),
    path('mrp/', include('apps.mrp.urls')),
    path('mes/', include('apps.mes.urls')),
    path('qms/', include('apps.qms.urls')),
    path('inventory/', include('apps.inventory.urls')),
    path('procurement/', include('apps.procurement.urls')),
    path('eam/', include('apps.eam.urls')),
    path('labor/', include('apps.labor.urls')),
    path('cost/', include('apps.cost.urls')),
    path('utility/', include('apps.utility.urls')),
    path('compliance/', include('apps.compliance.urls')),
    path('iot/', include('apps.iot.urls')),
    path('bi/', include('apps.bi.urls')),
    path('sales/', include('apps.sales.urls')),
    path('rma/', include('apps.rma.urls')),
    path('dms/', include('apps.dms.urls')),
    path('wfa/', include('apps.wfa.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
