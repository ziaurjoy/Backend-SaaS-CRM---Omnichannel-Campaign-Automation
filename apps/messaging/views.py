from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.tenants.utils import IsTenantMember, TenantModelViewSetMixin
from apps.messaging.models import Message, Integration
from apps.messaging.serializers import MessageSerializer, IntegrationSerializer

class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        # Filter messages belonging to the current active tenant
        return Message.objects.filter(lead__business=self.request.business).order_by('-created_at')

class IntegrationViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Integration.objects.all()
    serializer_class = IntegrationSerializer

    @action(detail=False, methods=['post'], url_path='connect_whatsapp')
    def connect_whatsapp(self, request):
        phone_number = request.data.get('phone_number')
        credentials = request.data.get('credentials', {})
        status_val = request.data.get('status', 'Connected')

        if not phone_number:
            return Response({'detail': 'phone_number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        integration, created = Integration.objects.update_or_create(
            business=request.business,
            provider='WhatsApp',
            defaults={
                'credentials': credentials,
                'status': status_val,
                'connected_phone': phone_number
            }
        )
        serializer = self.get_serializer(integration)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='connect_gmail')
    def connect_gmail(self, request):
        email = request.data.get('email')
        credentials = request.data.get('credentials', {})
        status_val = request.data.get('status', 'Connected')

        if not email:
            return Response({'detail': 'email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        integration, created = Integration.objects.update_or_create(
            business=request.business,
            provider='Gmail',
            defaults={
                'credentials': credentials,
                'status': status_val,
                'connected_email': email
            }
        )
        serializer = self.get_serializer(integration)
        return Response(serializer.data, status=status.HTTP_200_OK)
