import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# A booking longer than this is almost certainly a mistake (or someone
# parking a car indefinitely), so the form rejects it rather than silently
# holding a slot for weeks.
MAX_RESERVATION_HOURS = 24

# Bookings may start slightly in the past to absorb clock skew and the few
# seconds between loading the form and submitting it.
BACKDATE_GRACE_MINUTES = 5


def generate_reference():
    """Short, human-readable code security reads off a phone at the gate.

    Uppercase hex keeps it unambiguous when read aloud, and 6 characters is
    far more collision-resistant than the number of bookings this platform
    will ever hold at once.
    """
    return f'ATU-{secrets.token_hex(3).upper()}'


class Reservation(models.Model):
    """A booked parking slot for a specific vehicle over a specific window."""

    class Status(models.TextChoices):
        CONFIRMED = 'confirmed', 'Confirmed'
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'

    # Statuses that still hold the slot against other bookings. Anything
    # outside this set has released its claim, so the window is bookable
    # again — overlap checks and slot-status syncing both key off it.
    HOLDING_STATUSES = (Status.CONFIRMED, Status.ACTIVE)

    reference = models.CharField(
        max_length=12,
        unique=True,
        default=generate_reference,
        editable=False,
        help_text='Quoted at the gate for verification.',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    vehicle = models.ForeignKey(
        'vehicles.Vehicle',
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    slot = models.ForeignKey(
        'parking.ParkingSlot',
        on_delete=models.PROTECT,
        related_name='reservations',
        help_text='PROTECTed so deleting a zone can never erase booking history.',
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)

    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['slot', 'start_time', 'end_time']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.reference} — {self.vehicle.registration_number} @ {self.slot}'

    # -- derived state -----------------------------------------------------

    @property
    def zone(self):
        return self.slot.zone

    @property
    def is_holding(self):
        """True while this booking still has a claim on the slot."""
        return self.status in self.HOLDING_STATUSES

    @property
    def is_current(self):
        """True when now falls inside the booked window and it still holds."""
        return self.is_holding and self.start_time <= timezone.now() <= self.end_time

    @property
    def is_upcoming(self):
        return self.is_holding and self.start_time > timezone.now()

    @property
    def has_lapsed(self):
        """Window has passed without the booking being closed out."""
        return self.is_holding and self.end_time < timezone.now()

    @property
    def duration_hours(self):
        return round((self.end_time - self.start_time).total_seconds() / 3600, 1)

    @property
    def can_cancel(self):
        """Cancellable until the vehicle has actually checked in."""
        return self.status == self.Status.CONFIRMED

    @property
    def status_tone(self):
        """Bootstrap contextual suffix, so templates don't carry the mapping."""
        return {
            self.Status.CONFIRMED: 'primary',
            self.Status.ACTIVE: 'success',
            self.Status.COMPLETED: 'secondary',
            self.Status.CANCELLED: 'danger',
            self.Status.EXPIRED: 'warning',
        }[self.status]

    # -- validation --------------------------------------------------------

    def overlapping_reservations(self):
        """Other live bookings competing for the same slot and window.

        Two windows overlap when each starts before the other ends; touching
        endpoints (one ends exactly as the next starts) are not a clash, so
        back-to-back bookings on the same slot are allowed.
        """
        return (
            Reservation.objects
            .filter(
                slot=self.slot,
                status__in=self.HOLDING_STATUSES,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            )
            .exclude(pk=self.pk)
        )

    def clean(self):
        super().clean()
        errors = {}

        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                errors['end_time'] = 'The end time must be after the start time.'
            else:
                hours = (self.end_time - self.start_time).total_seconds() / 3600
                if hours > MAX_RESERVATION_HOURS:
                    errors['end_time'] = (
                        f'A single booking cannot exceed {MAX_RESERVATION_HOURS} hours.'
                    )

        if self.start_time and not self.pk:
            earliest = timezone.now() - timedelta(minutes=BACKDATE_GRACE_MINUTES)
            if self.start_time < earliest:
                errors['start_time'] = 'The start time cannot be in the past.'

        if self.user_id and self.vehicle_id and self.vehicle.owner_id != self.user_id:
            errors['vehicle'] = 'That vehicle is not registered to you.'

        if self.slot_id and self.start_time and self.end_time and 'end_time' not in errors:
            clash = self.overlapping_reservations().first()
            if clash is not None:
                errors['slot'] = (
                    f'{self.slot} is already booked from '
                    f'{timezone.localtime(clash.start_time):%d %b %H:%M} to '
                    f'{timezone.localtime(clash.end_time):%H:%M}. '
                    'Pick another slot or a different time.'
                )

        if errors:
            raise ValidationError(errors)
