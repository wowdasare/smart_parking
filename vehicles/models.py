from django.conf import settings
from django.db import models


class Vehicle(models.Model):
    class VehicleType(models.TextChoices):
        CAR = 'car', 'Car'
        MOTORCYCLE = 'motorcycle', 'Motorcycle'
        OTHER = 'other', 'Other'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vehicles',
    )
    registration_number = models.CharField(max_length=20, unique=True)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, default=VehicleType.CAR)
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    color = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.registration_number} ({self.make} {self.model})'

    def save(self, *args, **kwargs):
        self.registration_number = self.registration_number.upper().strip()
        super().save(*args, **kwargs)
