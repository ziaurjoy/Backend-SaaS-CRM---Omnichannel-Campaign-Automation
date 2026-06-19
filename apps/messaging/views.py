from rest_framework import viewsets, permissions
from apps.tenants.utils import IsTenantMember
from apps.messaging.models import Message
from apps.messaging.serializers import MessageSerializer

class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        # Filter messages belonging to the current active tenant
        return Message.objects.filter(lead__business=self.request.business).order_by('-created_at')
