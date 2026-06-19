import time
import random
import socket
from celery import shared_task
from django.utils import timezone
from apps.campaigns.models import CampaignRun
from apps.crm.models import Lead
from apps.messaging.models import Message

def is_redis_running():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        s.connect(('localhost', 6379))
        s.close()
        return True
    except Exception:
        return False

def render_template(body, lead):
    """
    Replaces variables like {{first_name}}, {{company_name}}, etc. in the body.
    """
    first_name = lead.name.split(' ')[0] if lead.name else ''
    last_name = lead.name.split(' ')[1] if lead.name and len(lead.name.split(' ')) > 1 else ''
    company_name = lead.name  # Fallback to lead name
    email = lead.email or ''
    phone = lead.phone or ''
    
    rendered = body
    rendered = rendered.replace('{{first_name}}', first_name)
    rendered = rendered.replace('{{last_name}}', last_name)
    rendered = rendered.replace('{{company_name}}', company_name)
    rendered = rendered.replace('{{email}}', email)
    rendered = rendered.replace('{{phone}}', phone)
    return rendered

@shared_task
def send_message_task(message_id):
    try:
        msg = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        return
        
    msg.status = 'Sent'
    msg.sent_at = timezone.now()
    msg.save()
    
    # Simulate delivery delay and success/failure (95% success rate)
    time.sleep(0.5)
    success = random.random() < 0.95
    if success:
        msg.status = 'Delivered'
        msg.delivered_at = timezone.now()
        msg.save()
        
        # Simulate open rate (60% open rate)
        if msg.channel == 'Email' or msg.channel == 'WhatsApp':
            if random.random() < 0.60:
                time.sleep(0.5)
                msg.status = 'Opened'
                msg.opened_at = timezone.now()
                msg.save()
    else:
        msg.status = 'Failed'
        msg.failed_reason = random.choice([
            "Connection timeout to server",
            "SMTP server authentication failed",
            "Invalid recipient format",
            "Recipient mailbox full"
        ])
        msg.save()

@shared_task
def execute_campaign_run_task(campaign_run_id):
    try:
        run = CampaignRun.objects.get(id=campaign_run_id)
    except CampaignRun.DoesNotExist:
        return
        
    campaign = run.campaign
    leads = Lead.objects.filter(business=campaign.business)
    
    if not leads.exists():
        run.status = 'Completed'
        run.completed_at = timezone.now()
        run.save()
        return

    # Process each lead
    for lead in leads:
        # Determine recipient address/number
        recipient = lead.email if campaign.channel == 'Email' else lead.phone
        if not recipient:
            continue
            
        rendered_body = render_template(campaign.template.body, lead)
        
        msg = Message.objects.create(
            campaign_run=run,
            lead=lead,
            template=campaign.template,
            channel=campaign.channel,
            recipient=recipient,
            status='Pending'
        )
        
        # Trigger sending.
        # Use delay() if Redis is running, otherwise call synchronously to avoid connection delays.
        if is_redis_running():
            try:
                send_message_task.delay(msg.id)
            except Exception:
                send_message_task(msg.id)
        else:
            send_message_task(msg.id)

    run.status = 'Completed'
    run.completed_at = timezone.now()
    run.save()
