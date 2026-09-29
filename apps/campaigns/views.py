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
        """
        Run / Pause toggle.
        - Active   → Paused  (mark paused; running task will check status and stop naturally)
        - Other    → Active  (resume or start; prevent duplicate workers)
        - Completed → 400
        """
        campaign = self.get_object()

        if campaign.status == 'Completed':
            return Response(
                {'detail': 'Campaign has already been completed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- PAUSE ---
        if campaign.status == 'Active':
            campaign.status = 'Paused'
            campaign.save(update_fields=['status'])
            serializer = CampaignSerializer(campaign)
            return Response(
                {'message': 'Campaign paused. Current message will finish sending.', 'campaign': serializer.data},
                status=status.HTTP_200_OK
            )

        # --- RUN / RESUME ---
        campaign.status = 'Active'
        campaign.save(update_fields=['status'])

        # Prevent duplicate workers: check for an already-running CampaignRun
        existing_run = CampaignRun.objects.filter(campaign=campaign, status='Running').first()
        if existing_run:
            serializer = CampaignRunSerializer(existing_run)
            return Response(
                {
                    'message': 'Campaign resumed. An active worker is already processing recipients.',
                    'async_execution': True,
                    'run': serializer.data,
                },
                status=status.HTTP_200_OK
            )

        # No active run — create a new one and dispatch
        run = CampaignRun.objects.create(campaign=campaign, status='Running')

        from apps.messaging.tasks import execute_campaign_run_task, is_redis_running
        executed_async = False
        if is_redis_running():
            try:
                execute_campaign_run_task.delay(run.id)
                executed_async = True
            except Exception:
                execute_campaign_run_task(run.id)
        else:
            execute_campaign_run_task(run.id)

        serializer = CampaignRunSerializer(run)
        return Response(
            {
                'message': 'Campaign started successfully.',
                'async_execution': executed_async,
                'run': serializer.data,
            },
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'], url_path='reset_recipient')
    def reset_recipient(self, request, pk=None):
        """
        Reset a single recipient (Message) so it can be re-sent.
        Prevents duplicate if the message is currently Processing.
        Does NOT restart the whole campaign.
        """
        campaign = self.get_object()
        message_id = request.data.get('message_id')
        if not message_id:
            return Response({'detail': 'message_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.messaging.models import Message
        try:
            msg = Message.objects.get(id=message_id, campaign_run__campaign=campaign)
        except Message.DoesNotExist:
            return Response({'detail': 'Recipient message not found for this campaign.'}, status=status.HTTP_404_NOT_FOUND)

        # Guard: do not reset if currently being processed
        if msg.status == 'Processing':
            return Response(
                {'detail': 'This recipient is currently being processed. Please wait for it to finish.'},
                status=status.HTTP_409_CONFLICT
            )

        # Reset the message back to Pending
        msg.status = 'Pending'
        msg.sent_at = None
        msg.delivered_at = None
        msg.opened_at = None
        msg.replied_at = None
        msg.failed_reason = None
        msg.is_replied = False
        msg.save()

        # Dispatch send task (existing pattern)
        from apps.messaging.tasks import send_message_task, is_redis_running
        if is_redis_running():
            try:
                send_message_task.delay(msg.id)
            except Exception:
                send_message_task(msg.id)
        else:
            send_message_task(msg.id)

        return Response({'detail': 'Recipient reset and queued for sending.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['delete'], url_path='delete_recipient')
    def delete_recipient(self, request, pk=None):
        """
        Safely delete a single recipient (Message row) from a campaign.
        Will not delete a message that is currently Processing.
        """
        campaign = self.get_object()
        message_id = request.data.get('message_id')
        if not message_id:
            return Response({'detail': 'message_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.messaging.models import Message
        try:
            msg = Message.objects.get(id=message_id, campaign_run__campaign=campaign)
        except Message.DoesNotExist:
            return Response({'detail': 'Recipient message not found for this campaign.'}, status=status.HTTP_404_NOT_FOUND)

        if msg.status == 'Processing':
            return Response(
                {'detail': 'Cannot delete a recipient that is currently being processed.'},
                status=status.HTTP_409_CONFLICT
            )

        msg.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

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
