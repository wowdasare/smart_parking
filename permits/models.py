from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import dateformat, timezone


class PermitQuerySet(models.QuerySet):
    def active(self):
        """Permits that are approved and inside their validity window.

        Status alone isn't enough: a permit stays ACTIVE in the database
        until something sweeps it to EXPIRED, so the date bounds are checked
        here too. That makes this queryset safe to trust at the gate even if
        the expiry sweep hasn't run yet.
        """
        today = timezone.localdate()
        return self.filter(
            status=Permit.Status.ACTIVE,
            valid_from__lte=today,
            valid_until__gte=today,
        )

    def for_plate(self, plate_number):
        """Gate lookup: whoever is driving, does this plate have cover?"""
        return self.filter(vehicle__registration_number__iexact=plate_number.strip())

    def awaiting_review(self):
        return self.filter(status=Permit.Status.PENDING)


class Permit(models.Model):
    """A permit authorising one vehicle to park on campus for a period.

    Separate from Reservation deliberately: a permit is the standing right to
    park at all (a term or year at a time, paid for, approved by staff),
    while a reservation is one specific bay for one specific afternoon.
    """

    class PermitType(models.TextChoices):
        STUDENT = 'student', 'Student — semester'
        STAFF = 'staff', 'Staff — academic year'
        VISITOR = 'visitor', 'Visitor — short stay'
        CONTRACTOR = 'contractor', 'Contractor — project duration'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending review'
        ACTIVE = 'active', 'Active'
        REJECTED = 'rejected', 'Rejected'
        EXPIRED = 'expired', 'Expired'
        REVOKED = 'revoked', 'Revoked'

    # Statuses that block a second permit on the same vehicle. A rejected or
    # revoked application shouldn't stop the holder from reapplying.
    BLOCKING_STATUSES = (Status.PENDING, Status.ACTIVE)

    # Standard fees in Ghana cedis, by permit type. Kept here rather than in
    # settings because changing a fee is a data/policy decision the finance
    # office makes per application, not a deployment config.
    DEFAULT_FEES = {
        PermitType.STUDENT: 50,
        PermitType.STAFF: 120,
        PermitType.VISITOR: 10,
        PermitType.CONTRACTOR: 200,
    }

    permit_number = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text='Assigned on approval, e.g. ATU-P-2026-0001.',
    )
    holder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='permits',
    )
    vehicle = models.ForeignKey(
        'vehicles.Vehicle',
        on_delete=models.CASCADE,
        related_name='permits',
    )
    permit_type = models.CharField(max_length=20, choices=PermitType.choices, default=PermitType.STUDENT)
    zone = models.ForeignKey(
        'parking.Zone',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='permits',
        help_text='Leave blank for a permit valid in any zone.',
    )

    valid_from = models.DateField()
    valid_until = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    fee_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)

    applicant_note = models.CharField(max_length=255, blank=True, help_text='Anything staff should know.')
    document = models.FileField(
        upload_to='permits/%Y/%m/',
        blank=True,
        help_text='Supporting document — student ID, appointment letter, etc.',
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_permits',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True, help_text='Reason shown to the applicant.')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PermitQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['valid_from', 'valid_until']),
        ]

    def __str__(self):
        label = self.permit_number or f'Application #{self.pk}'
        return f'{label} — {self.vehicle.registration_number} ({self.get_status_display()})'

    # -- derived state -----------------------------------------------------

    @property
    def is_current(self):
        """Approved and inside its dates — the question the gate asks."""
        today = timezone.localdate()
        return self.status == self.Status.ACTIVE and self.valid_from <= today <= self.valid_until

    @property
    def has_lapsed(self):
        return self.status == self.Status.ACTIVE and self.valid_until < timezone.localdate()

    @property
    def days_remaining(self):
        """Days of cover left; negative once the window has passed."""
        return (self.valid_until - timezone.localdate()).days

    @property
    def expires_soon(self):
        return self.is_current and 0 <= self.days_remaining <= 14

    @property
    def status_tone(self):
        """Bootstrap contextual suffix, so templates don't carry the mapping."""
        return {
            self.Status.PENDING: 'warning',
            self.Status.ACTIVE: 'success',
            self.Status.REJECTED: 'danger',
            self.Status.EXPIRED: 'secondary',
            self.Status.REVOKED: 'dark',
        }[self.status]

    @property
    def zone_label(self):
        return self.zone.name if self.zone else 'All zones'

    @staticmethod
    def _step_when(value):
        """Formats a step's timestamp for display.

        The timeline mixes DateTimeFields (created_at, reviewed_at) with a
        DateField (valid_until), and Django's date filter raises on a date
        given a time specifier — so the choice of format has to be made here,
        where the type is still known.
        """
        if value is None:
            return None
        if isinstance(value, datetime):     # datetime is a subclass of date
            return dateformat.format(timezone.localtime(value), 'j M Y, H:i')
        return dateformat.format(value, 'j M Y')

    @property
    def timeline(self):
        """Application progress as ordered steps, for the detail page.

        Built here rather than in the template because the outcome step
        depends on the status in a way that would need a chain of {% if %}
        branches to express, and the same shape is useful anywhere the
        application's history is shown.
        """
        steps = [{
            'label': 'Application submitted',
            'when': self._step_when(self.created_at),
            'state': 'is-done',
            'icon': 'bi-send-check',
        }]

        if self.reviewed_at:
            steps.append({
                'label': 'Reviewed by parking office',
                'when': self._step_when(self.reviewed_at),
                'state': 'is-done',
                'icon': 'bi-clipboard-check',
            })
        else:
            steps.append({
                'label': 'Awaiting office review',
                'when': None,
                'state': 'is-current',
                'icon': 'bi-hourglass-split',
            })

        outcomes = {
            self.Status.PENDING: ('Decision', None, 'is-upcoming', 'bi-question-circle'),
            self.Status.ACTIVE: ('Permit issued', self.reviewed_at, 'is-done', 'bi-patch-check'),
            self.Status.REJECTED: ('Application declined', self.reviewed_at, 'is-failed', 'bi-x-circle'),
            self.Status.REVOKED: ('Permit revoked', self.reviewed_at, 'is-failed', 'bi-slash-circle'),
            self.Status.EXPIRED: ('Permit expired', self.valid_until, 'is-done', 'bi-hourglass-bottom'),
        }
        label, when, state, icon = outcomes[self.status]
        steps.append({'label': label, 'when': self._step_when(when), 'state': state, 'icon': icon})

        if self.status == self.Status.ACTIVE:
            steps.append({
                'label': 'Cover ends',
                'when': self._step_when(self.valid_until),
                'state': 'is-upcoming',
                'icon': 'bi-calendar-x',
            })

        return steps

    @property
    def can_be_reviewed(self):
        return self.status == self.Status.PENDING

    @property
    def can_be_revoked(self):
        return self.status == self.Status.ACTIVE

    @property
    def can_be_withdrawn(self):
        """The holder may pull their own application before it's decided."""
        return self.status == self.Status.PENDING

    # -- validation --------------------------------------------------------

    def blocking_permits(self):
        """Other pending/active permits already covering this vehicle."""
        return (
            Permit.objects
            .filter(
                vehicle=self.vehicle,
                status__in=self.BLOCKING_STATUSES,
                valid_from__lte=self.valid_until,
                valid_until__gte=self.valid_from,
            )
            .exclude(pk=self.pk)
        )

    def clean(self):
        super().clean()
        errors = {}

        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            errors['valid_until'] = 'The end date cannot be before the start date.'

        if self.holder_id and self.vehicle_id and self.vehicle.owner_id != self.holder_id:
            errors['vehicle'] = 'That vehicle is not registered to you.'

        if self.vehicle_id and self.valid_from and self.valid_until and 'valid_until' not in errors:
            clash = self.blocking_permits().first()
            if clash is not None:
                errors['vehicle'] = (
                    f'{self.vehicle.registration_number} already has cover '
                    f'({clash.get_status_display().lower()}) from '
                    f'{clash.valid_from:%d %b %Y} to {clash.valid_until:%d %b %Y}.'
                )

        if errors:
            raise ValidationError(errors)
