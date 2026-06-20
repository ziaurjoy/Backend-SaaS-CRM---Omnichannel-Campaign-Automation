from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.campaigns.views import CampaignViewSet, CampaignRunViewSet

router = DefaultRouter()
router.register(r'runs', CampaignRunViewSet, basename='campaignrun')
router.register(r'', CampaignViewSet, basename='campaign')

urlpatterns = [
    path('', include(router.urls)),
]
