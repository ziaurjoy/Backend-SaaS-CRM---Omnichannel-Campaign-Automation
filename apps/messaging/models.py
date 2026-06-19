from django.db import models
from apps.crm.models import Lead
from apps.templates.models import Template
from apps.campaigns.models import CampaignRun

class Message(models.Model):
    CHANNEL_CHOICES = (
        ('Email', 'Email'),
        ('WhatsApp', 'WhatsApp'),
    )
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Sent', 'Sent'),
        ('Delivered', 'Delivered'),
        ('Opened', 'Opened'),
        ('Failed', 'Failed'),
    )
    campaign_run = models.ForeignKey(CampaignRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='messages')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='messages')
    template = models.ForeignKey(Template, on_delete=models.SET_NULL, null=True, blank=True, related_name='messages')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    recipient = models.CharField(max_length=255)  # Email or Phone number
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    sent_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    opened_at = models.DateTimeField(blank=True, null=True)
    failed_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.channel} to {self.recipient} ({self.status})"
