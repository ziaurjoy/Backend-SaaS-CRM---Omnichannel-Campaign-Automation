from django.db import models
from django.conf import settings
from apps.tenants.models import Business

class Tag(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=50)

    class Meta:
        unique_together = ('business', 'name')

    def __str__(self):
        return f"{self.name} ({self.business.name})"

class LeadCollection(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='collections')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('business', 'name')

    def __str__(self):
        return f"{self.name} ({self.business.name})"

class GooglePlaceScrapeSession(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Running', 'Running'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
    )
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='places_scrape_sessions')
    collection = models.ForeignKey(LeadCollection, on_delete=models.SET_NULL, null=True, blank=True, related_name='places_scrape_sessions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    query = models.CharField(max_length=255)
    page_size = models.PositiveIntegerField(default=20)
    pages_fetched = models.PositiveIntegerField(default=0)
    total_scraped = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Scrape '{self.query}' ({self.status}) - {self.business.name}"

class Lead(models.Model):
    STAGE_CHOICES = (
        ('New', 'New'),
        ('Contacted', 'Contacted'),
        ('Qualified', 'Qualified'),
        ('Proposal', 'Proposal'),
        ('Won', 'Won'),
        ('Lost', 'Lost'),
    )
    STATUS_CHOICES = (
        ('Lead', 'Lead'),
        ('Customer', 'Customer'),
    )
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='leads')
    collection = models.ForeignKey(LeadCollection, on_delete=models.CASCADE, related_name='leads', null=True, blank=True)
    scrape_session = models.ForeignKey(GooglePlaceScrapeSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True)
    source = models.CharField(max_length=100, default='Manual')
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='New')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Lead')
    tags = models.ManyToManyField(Tag, blank=True, related_name='leads')
    
    # Google Places API Metadata
    place_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    user_ratings_total = models.IntegerField(blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    business_status = models.CharField(max_length=50, blank=True, null=True)
    types = models.JSONField(default=list, blank=True)
    primary_type = models.CharField(max_length=100, blank=True, null=True)
    primary_type_display_name = models.CharField(max_length=100, blank=True, null=True)
    price_level = models.CharField(max_length=50, blank=True, null=True)
    google_metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'place_id']),
            models.Index(fields=['business', 'name']),
            models.Index(fields=['business', 'stage']),
            models.Index(fields=['business', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'place_id'],
                condition=models.Q(place_id__isnull=False) & ~models.Q(place_id=''),
                name='unique_business_place_id'
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.business.name}"

class LeadActivity(models.Model):
    ACTIVITY_TYPE_CHOICES = (
        ('Log', 'Log'),
        ('Call', 'Call'),
        ('Email', 'Email'),
        ('SMS', 'SMS'),
        ('WhatsApp', 'WhatsApp'),
        ('Note', 'Note'),
        ('StageChange', 'StageChange'),
    )
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPE_CHOICES, default='Log')
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.activity_type} for {self.lead.name} at {self.created_at}"
