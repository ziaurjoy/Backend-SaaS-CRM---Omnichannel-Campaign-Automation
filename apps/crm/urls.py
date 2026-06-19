from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.crm.views import LeadViewSet, TagViewSet

router = DefaultRouter()
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'leads', LeadViewSet, basename='lead')

urlpatterns = [
    path('', include(router.urls)),
]
