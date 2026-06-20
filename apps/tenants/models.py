import uuid
from django.db import models
from django.conf import settings

class Business(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    logo = models.CharField(max_length=500, blank=True, null=True)  # URL or path
    industry = models.CharField(max_length=100, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    timezone = models.CharField(max_length=50, default='UTC')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Businesses"

    def __str__(self):
        return self.name

class BusinessMember(models.Model):
    ROLE_CHOICES = (
        ('Owner', 'Owner'),
        ('Admin', 'Admin'),
        ('Member', 'Member'),
    )
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='business_memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='Member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('business', 'user')

    def __str__(self):
        return f"{self.user.username} - {self.business.name} ({self.role})"
