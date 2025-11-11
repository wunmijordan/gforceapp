# notifications/models.py
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from accounts.models import CustomUser
from django.utils import timezone


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    link = models.URLField(blank=True, null=True)
    is_read = models.BooleanField(default=False)
    is_urgent = models.BooleanField(default=False)
    is_success = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.username}"



class UserSettings(models.Model):
    SOUND_CHOICES = [
        ('chime1', 'Chime 1'),
        ('chime2', 'Chime 2'),
        ('chime3', 'Chime 3'),
        ('chime4', 'Chime 4'),
        ('chime5', 'Chime 5'),
        ('chime6', 'Chime 6'),
        ('chime7', 'Chime 7'),
        ('chime8', 'Chime 8'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="settings")
    notification_sound = models.CharField(max_length=20, choices=SOUND_CHOICES, default='chime1')
    vibration_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"Settings for {self.user.username}"


class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    subscription_data = models.JSONField()  # stores endpoint + keys
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PushSubscription for {self.user}"
