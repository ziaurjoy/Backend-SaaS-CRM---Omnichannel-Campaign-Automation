from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from apps.tenants.utils import TenantModelViewSetMixin
from apps.campaigns.models import Campaign, CampaignRun
from apps.campaigns.serializers import CampaignSerializer, CampaignRunSerializer

class CampaignViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer

    @action(detail=True, methods=['post'], url_path='trigger')
    def trigger_campaign(self, request, pk=None):
        campaign = self.get_object()
        
        # Check if campaign already completed
        if campaign.status == 'Completed':
            return Response({'detail': 'Campaign has already been completed.'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Update campaign status
        campaign.status = 'Active'
        campaign.save()

        # Create campaign run
        run = CampaignRun.objects.create(
            campaign=campaign,
            status='Running'
        )

        # Execute Celery task with synchronous fallback
        from apps.messaging.tasks import execute_campaign_run_task, is_redis_running
        if is_redis_running():
            try:
                execute_campaign_run_task.delay(run.id)
                executed_async = True
            except Exception as e:
                execute_campaign_run_task(run.id)
                executed_async = False
        else:
            execute_campaign_run_task(run.id)
            executed_async = False

        serializer = CampaignRunSerializer(run)
        return Response({
            "message": "Campaign triggered successfully.",
            "async_execution": executed_async,
            "run": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='messages')
    def get_messages(self, request, pk=None):
        campaign = self.get_object()
        from apps.messaging.models import Message
        from apps.messaging.serializers import MessageSerializer
        
        messages = Message.objects.filter(
            campaign_run__campaign=campaign
        ).select_related('lead', 'campaign_run', 'campaign_run__campaign')
        
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CampaignRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CampaignRunSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Return campaign runs belonging to the user's active tenant
        business_id = self.request.headers.get('X-Business-ID') or self.request.query_params.get('business_id')
        if not business_id:
            return CampaignRun.objects.none()
        return CampaignRun.objects.filter(campaign__business_id=business_id)
