import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def generate_api_key():
    return secrets.token_hex(20)


class SensorDevice(models.Model):
    """A physical IoT device (slot sensor, gate sensor, etc.) authorized to
    report data via the sensor API.
    """

    class DeviceType(models.TextChoices):
        SLOT_SENSOR = 'slot_sensor', 'Slot Sensor'
        GATE_SENSOR = 'gate_sensor', 'Gate Sensor'

    device_id = models.CharField(max_length=64, unique=True, help_text='Identifier printed on/flashed to the device, e.g. "ESP32-A1B2C3".')
    api_key = models.CharField(max_length=64, unique=True, default=generate_api_key, editable=False)
    device_type = models.CharField(max_length=20, choices=DeviceType.choices, default=DeviceType.SLOT_SENSOR)

    # A slot has at most one sensor (OneToOne); a zone can have several gate
    # sensors, e.g. separate entry and exit units (plain ForeignKey).
    slot = models.OneToOneField(
        'parking.ParkingSlot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sensor_device',
        help_text='Required for slot sensors.',
    )
    zone = models.ForeignKey(
        'parking.Zone',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gate_sensors',
        help_text='Required for gate sensors (a zone may have more than one, e.g. entry + exit).',
    )

    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.device_id

    def clean(self):
        if self.device_type == self.DeviceType.SLOT_SENSOR:
            if not self.slot_id:
                raise ValidationError({'slot': 'Slot sensors must be assigned to a slot.'})
            if self.zone_id:
                raise ValidationError({'zone': 'Slot sensors take their zone from their slot — leave this blank.'})
        elif self.device_type == self.DeviceType.GATE_SENSOR:
            if not self.zone_id:
                raise ValidationError({'zone': 'Gate sensors must be assigned to a zone.'})
            if self.slot_id:
                raise ValidationError({'slot': 'Gate sensors monitor a whole zone, not one slot — leave this blank.'})

    @property
    def is_online(self):
        """Derived from last_seen_at rather than stored, so it can't go stale
        (a stored flag could say "online" forever if a device just died)."""
        if not self.last_seen_at:
            return False
        threshold = timezone.now() - timedelta(minutes=settings.SENSOR_OFFLINE_THRESHOLD_MINUTES)
        return self.last_seen_at >= threshold

    @property
    def is_authenticated(self):
        """Duck-types Django's User.is_authenticated so DRF's IsAuthenticated
        permission works for a device that isn't a Django User."""
        return True


class GateEvent(models.Model):
    """A single vehicle entry/exit observed by a gate sensor.

    Kept as a raw log (separate from Zone.current_occupancy, which is just
    the running counter) so plate_number has somewhere real to land now,
    ahead of future permit cross-checking.
    """

    class EventType(models.TextChoices):
        ENTRY = 'entry', 'Entry'
        EXIT = 'exit', 'Exit'

    zone = models.ForeignKey('parking.Zone', on_delete=models.CASCADE, related_name='gate_events')
    device = models.ForeignKey(SensorDevice, on_delete=models.SET_NULL, null=True, blank=True, related_name='gate_events')
    event_type = models.CharField(max_length=10, choices=EventType.choices)
    plate_number = models.CharField(max_length=20, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return f'{self.get_event_type_display()} @ {self.zone} ({self.recorded_at:%Y-%m-%d %H:%M})'
