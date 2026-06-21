import time
import random
import socket
import base64
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
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

def send_gmail_via_api(access_token, from_email, to_email, subject, body_text):
    try:
        # Create MIME message
        mime_msg = MIMEMultipart()
        mime_msg['to'] = to_email
        mime_msg['from'] = from_email
        mime_msg['subject'] = subject
        
        mime_msg.attach(MIMEText(body_text, 'plain'))
        
        # Base64url encode the message bytes
        raw_bytes = mime_msg.as_bytes()
        encoded_raw = base64.urlsafe_b64encode(raw_bytes).decode('utf-8')
        
        url = "https://www.googleapis.com/gmail/v1/users/me/messages/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "raw": encoded_raw
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            return True, response.json()
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return False, str(e)

def get_fresh_gmail_token(integration):
    import os
    credentials = integration.credentials or {}
    access_token = credentials.get('access_token') or credentials.get('oauth_token')
    refresh_token = credentials.get('refresh_token')
    
    # If no refresh token or if it's a mock token, return whatever token we have
    if not refresh_token or (access_token and access_token.startswith("mock_")):
        return access_token
        
    expires_at = credentials.get('expires_at')
    # If the token is not expired (has more than 2 minutes left), return it
    if expires_at and time.time() < (expires_at - 120):
        return access_token
        
    # Otherwise, attempt to refresh the token using refresh token
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
    
    if not client_id or not client_secret:
        client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')
        
    if not client_id or not client_secret:
        return access_token
        
    url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            new_access_token = res_data.get('access_token')
            if new_access_token:
                credentials['access_token'] = new_access_token
                expires_in = res_data.get('expires_in', 3600)
                credentials['expires_at'] = time.time() + expires_in
                integration.credentials = credentials
                integration.save(update_fields=['credentials'])
                return new_access_token
    except Exception as e:
        print(f"Error refreshing Google token: {e}")
        
    return access_token

@shared_task
def send_message_task(message_id):
    try:
        msg = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        return
        
    msg.status = 'Sent'
    msg.sent_at = timezone.now()
    msg.save()

    # Determine details
    business = msg.campaign_run.campaign.business if (msg.campaign_run and msg.campaign_run.campaign) else None
    campaign = msg.campaign_run.campaign if (msg.campaign_run and msg.campaign_run.campaign) else None
    
    # Render body
    if campaign:
        body_template = campaign.message_content if campaign.message_content else (campaign.template.body if campaign.template else '')
        subject_template = campaign.template.subject if (campaign.template and campaign.template.subject) else "Campaign Outreach"
    elif msg.template:
        body_template = msg.template.body
        subject_template = msg.template.subject or "Outreach Message"
    else:
        body_template = ""
        subject_template = "Outreach Message"
        
    body = render_template(body_template, msg.lead) if msg.lead else body_template
    subject = render_template(subject_template, msg.lead) if msg.lead else subject_template
    recipient = msg.recipient

    # Check for real sending if Email
    sent_real = False
    gmail_error = None
    
    if msg.channel == 'Email':
        from apps.messaging.models import Integration
        gmail_integration = None
        if business:
            try:
                gmail_integration = Integration.objects.get(business=business, provider='Gmail', status='Connected')
            except Integration.DoesNotExist:
                pass
                
        if gmail_integration:
            access_token = get_fresh_gmail_token(gmail_integration)
            from_email = gmail_integration.connected_email or "me"
            
            if access_token and not access_token.startswith("mock_"):
                # Send real email via Google API
                success, err_msg = send_gmail_via_api(access_token, from_email, recipient, subject, body)
                if success:
                    sent_real = True
                else:
                    gmail_error = f"Gmail API error: {err_msg}"
            else:
                # Mock token or mock credentials, fall back to SMTP check or simulation
                pass

        # If Gmail API wasn't used or failed, check standard Django SMTP configuration
        if not sent_real and not gmail_error:
            if getattr(settings, 'EMAIL_HOST', None):
                try:
                    send_mail(
                        subject,
                        body,
                        getattr(settings, 'EMAIL_HOST_USER', 'noreply@omnicampaign.com'),
                        [recipient],
                        fail_silently=False,
                    )
                    sent_real = True
                except Exception as smtp_err:
                    gmail_error = f"SMTP error: {str(smtp_err)}"

    # Set status
    if msg.channel == 'Email' and (sent_real or not gmail_error):
        # Successfully sent via Gmail API or SMTP (or simulated fallback)
        msg.status = 'Delivered'
        msg.delivered_at = timezone.now()
        msg.save()
        
        # Simulate open rate (60% open rate)
        if random.random() < 0.60:
            time.sleep(0.5)
            msg.status = 'Opened'
            msg.opened_at = timezone.now()
            msg.save()
            
            # Simulate response/reply (25% reply rate if opened)
            if random.random() < 0.25:
                time.sleep(0.5)
                msg.status = 'Replied'
                msg.is_replied = True
                msg.replied_at = timezone.now()
                msg.save()
                
    elif msg.channel == 'Email' and gmail_error:
        # Failed real sending
        msg.status = 'Failed'
        msg.failed_reason = gmail_error
        msg.save()
        
    else:
        # WhatsApp or other channel -> simulated sending as before
        time.sleep(0.5)
        success = random.random() < 0.95
        if success:
            msg.status = 'Delivered'
            msg.delivered_at = timezone.now()
            msg.save()
            
            # Simulate open rate (60% open rate)
            if random.random() < 0.60:
                time.sleep(0.5)
                msg.status = 'Opened'
                msg.opened_at = timezone.now()
                msg.save()
                
                # Simulate response/reply (25% reply rate if opened)
                if random.random() < 0.25:
                    time.sleep(0.5)
                    msg.status = 'Replied'
                    msg.is_replied = True
                    msg.replied_at = timezone.now()
                    msg.save()
        else:
            msg.status = 'Failed'
            msg.failed_reason = random.choice([
                "Connection timeout to server",
                "API service authentication failed",
                "Invalid recipient format"
            ])
            msg.save()

@shared_task
def execute_campaign_run_task(campaign_run_id):
    try:
        run = CampaignRun.objects.get(id=campaign_run_id)
    except CampaignRun.DoesNotExist:
        return
        
    campaign = run.campaign
    if campaign.target_collection:
        leads = Lead.objects.filter(business=campaign.business, collection=campaign.target_collection)
    else:
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
            
        body_content = campaign.message_content if campaign.message_content else (campaign.template.body if campaign.template else '')
        rendered_body = render_template(body_content, lead)
        
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
