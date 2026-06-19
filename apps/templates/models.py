from django.db import models
from apps.tenants.models import Business

class Template(models.Model):
    TEMPLATE_TYPE_CHOICES = (
        ('Email', 'Email'),
        ('WhatsApp', 'WhatsApp'),
    )
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='templates')
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=TEMPLATE_TYPE_CHOICES)
    subject = models.CharField(max_length=255, blank=True, null=True)  # Used for Email
    body = models.TextField()  # Content with variables like {{first_name}}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.type}) - {self.business.name}"
