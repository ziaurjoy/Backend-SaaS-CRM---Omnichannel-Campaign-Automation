from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.messaging.views import MessageViewSet

router = DefaultRouter()
router.register(r'', MessageViewSet, basename='message')

urlpatterns = [
    path('', include(router.urls)),
]
