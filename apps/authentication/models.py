from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    profile_photo = models.CharField(max_length=500, blank=True, null=True)
    timezone = models.CharField(max_length=50, default='UTC')

    def __str__(self):
        return self.username
