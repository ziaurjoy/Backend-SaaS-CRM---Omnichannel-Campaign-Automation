from django.urls import path
from apps.analytics.views import DashboardMetricsView

urlpatterns = [
    path('dashboard/', DashboardMetricsView.as_view(), name='dashboard_metrics'),
]
