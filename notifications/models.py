from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Category(models.TextChoices):
        BOOKING = 'booking', 'Booking'
        STATUS_CHANGE = 'status_change', 'Status Change'
        SYSTEM = 'system', 'System'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SYSTEM)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient}: {self.message[:50]}'
