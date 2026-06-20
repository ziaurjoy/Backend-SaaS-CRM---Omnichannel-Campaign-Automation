from django.db import models
from django.conf import settings
from apps.tenants.models import Business

class AuditLog(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    details = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} by {self.user.username if self.user else 'System'} at {self.created_at}"
