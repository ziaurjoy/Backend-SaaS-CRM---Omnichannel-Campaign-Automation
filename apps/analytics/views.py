from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from apps.tenants.utils import IsTenantMember
from apps.crm.models import Lead
from apps.campaigns.models import Campaign, CampaignRun
from apps.messaging.models import Message

class DashboardMetricsView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request, *args, **kwargs):
        business = request.business

        # Lead metrics
        total_leads = Lead.objects.filter(business=business).count()
        leads_by_stage = Lead.objects.filter(business=business).values('stage').annotate(count=Count('id'))
        stage_counts = {choice[0]: 0 for choice in Lead.STAGE_CHOICES}
        for item in leads_by_stage:
            stage_counts[item['stage']] = item['count']

        # Campaigns
        total_campaigns = Campaign.objects.filter(business=business).count()
        active_campaigns = Campaign.objects.filter(business=business, status='Active').count()
        completed_campaigns = Campaign.objects.filter(business=business, status='Completed').count()

        # Messages metrics
        messages_qs = Message.objects.filter(lead__business=business)
        total_messages = messages_qs.count()
        sent_messages = messages_qs.filter(status='Sent').count()
        delivered_messages = messages_qs.filter(status='Delivered').count()
        opened_messages = messages_qs.filter(status='Opened').count()
        failed_messages = messages_qs.filter(status='Failed').count()

        # Rates calculation
        delivery_rate = 0.0
        open_rate = 0.0
        
        sent_or_delivered = sent_messages + delivered_messages + opened_messages
        if total_messages > 0:
            delivery_rate = round((sent_or_delivered / total_messages) * 100, 2)
            
        if sent_or_delivered > 0:
            open_rate = round((opened_messages / sent_or_delivered) * 100, 2)

        # Lead growth (last 7 days)
        today = timezone.now().date()
        lead_growth = []
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            count = Lead.objects.filter(business=business, created_at__date=date).count()
            lead_growth.append({
                "date": date.strftime("%b %d"),
                "count": count
            })

        return Response({
            "leads": {
                "total": total_leads,
                "by_stage": stage_counts
            },
            "campaigns": {
                "total": total_campaigns,
                "active": active_campaigns,
                "completed": completed_campaigns
            },
            "messages": {
                "total": total_messages,
                "sent": sent_messages,
                "delivered": delivered_messages,
                "opened": opened_messages,
                "failed": failed_messages,
                "delivery_rate": delivery_rate,
                "open_rate": open_rate
            },
            "lead_growth": lead_growth
        })
