from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.authentication.urls')),
    path('api/businesses/', include('apps.tenants.urls')),
    
    # Mount CRM endpoints directly
    path('api/', include('apps.crm.urls')),
    
    # Mount template endpoints
    path('api/templates/', include('apps.templates.urls')),
    
    # Mount campaign endpoints
    path('api/campaigns/', include('apps.campaigns.urls')),
    
    # Mount messaging endpoints
    path('api/messages/', include('apps.messaging.urls')),
    
    # Mount analytics endpoints
    path('api/analytics/', include('apps.analytics.urls')),
]
