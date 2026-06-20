from django.db import models
from apps.tenants.models import Business
from apps.templates.models import Template

class Campaign(models.Model):
    STATUS_CHOICES = (
        ('Draft', 'Draft'),
        ('Active', 'Active'),
        ('Paused', 'Paused'),
        ('Completed', 'Completed'),
    )
    CHANNEL_CHOICES = (
        ('Email', 'Email'),
        ('WhatsApp', 'WhatsApp'),
    )
    SCHEDULE_TYPE_CHOICES = (
        ('Immediate', 'Immediate'),
        ('Scheduled', 'Scheduled'),
    )
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='campaigns')
    name = models.CharField(max_length=255)
    template = models.ForeignKey(Template, on_delete=models.PROTECT, related_name='campaigns')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPE_CHOICES, default='Immediate')
    scheduled_time = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.status}) - {self.business.name}"

class CampaignRun(models.Model):
    RUN_STATUS_CHOICES = (
        ('Running', 'Running'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
    )
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='runs')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=RUN_STATUS_CHOICES, default='Running')

    def __str__(self):
        return f"Run {self.id} for {self.campaign.name} ({self.status})"
