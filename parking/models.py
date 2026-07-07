from django.conf import settings
from django.db import models
from django.utils import timezone


class Zone(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True, help_text='Short identifier, e.g. "A", "NORTH".')
    description = models.CharField(max_length=255, blank=True)

    # Gate-level occupancy, tracked independently from individual slot
    # statuses — a zone may be gate-counted without every bay having its own
    # slot sensor, so these two signals can legitimately diverge.
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text='Total vehicle capacity, if known.')
    current_occupancy = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


class ParkingSlot(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        OCCUPIED = 'occupied', 'Occupied'
        RESERVED = 'reserved', 'Reserved'

    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='slots')
    slot_number = models.CharField(max_length=10)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    manual_override_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last time a human manually set this status. Conflicting sensor '
                   'reports are deferred for MANUAL_OVERRIDE_GRACE_MINUTES after this.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['zone', 'slot_number']
        unique_together = ('zone', 'slot_number')

    def __str__(self):
        return f'{self.zone.code}-{self.slot_number}'

    def save(self, *args, **kwargs):
        """Keeps status_changed_at accurate no matter which code path saves
        the slot (Django admin, the sensor API, shell, future views) — a
        single source of truth instead of every caller remembering to set it.
        """
        if self.pk:
            old_status = ParkingSlot.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if old_status is not None and old_status != self.status:
                self.status_changed_at = timezone.now()
        else:
            self.status_changed_at = timezone.now()
        super().save(*args, **kwargs)


class SlotStatusChangeLog(models.Model):
    """Append-only record of every applied status change and every sensor
    report rejected due to conflict resolution — kept separate from
    ParkingSlot itself so history survives regardless of the slot's current
    state, and so sensor-sourced vs. manual changes can be analyzed apart.
    """

    class Source(models.TextChoices):
        SENSOR = 'sensor', 'Sensor'
        MANUAL = 'manual', 'Manual'

    slot = models.ForeignKey(ParkingSlot, on_delete=models.CASCADE, related_name='status_change_logs')
    source = models.CharField(max_length=10, choices=Source.choices)
    device_id = models.CharField(max_length=64, blank=True, help_text='Set when source is sensor.')
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Set when source is manual.',
    )
    previous_status = models.CharField(max_length=20, choices=ParkingSlot.Status.choices)
    attempted_status = models.CharField(max_length=20, choices=ParkingSlot.Status.choices)
    applied = models.BooleanField(default=True, help_text='False means rejected due to an active manual override.')
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        verb = f'{self.previous_status} → {self.attempted_status}' if self.applied else f'rejected ({self.attempted_status})'
        return f'{self.slot} [{self.source}]: {verb}'
