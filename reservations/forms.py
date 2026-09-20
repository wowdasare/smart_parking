from datetime import timedelta

from django import forms
from django.utils import timezone

from accounts.forms import BootstrapFormMixin
from parking.models import ParkingSlot

from .models import Reservation


class ReservationForm(BootstrapFormMixin, forms.ModelForm):
    """Booking form, scoped to one user's own vehicles.

    The user is passed in rather than being a form field so a booker can
    never submit someone else's vehicle by editing the POST payload.
    """

    class Meta:
        model = Reservation
        fields = ('vehicle', 'slot', 'start_time', 'end_time')
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }
        labels = {
            'vehicle': 'Which vehicle?',
            'slot': 'Parking slot',
            'start_time': 'Arriving at',
            'end_time': 'Leaving by',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        self.fields['vehicle'].queryset = user.vehicles.all()
        self.fields['vehicle'].empty_label = 'Select a vehicle'

        # Occupied bays are excluded: they are physically in use right now,
        # so offering them would invite a clash the booker can't see. Slots
        # merely RESERVED stay bookable — the overlap check on the model
        # decides whether the requested window actually conflicts.
        self.fields['slot'].queryset = (
            ParkingSlot.objects
            .select_related('zone')
            .exclude(status=ParkingSlot.Status.OCCUPIED)
            .order_by('zone__name', 'slot_number')
        )
        self.fields['slot'].empty_label = 'Select a slot'
        self.fields['slot'].help_text = 'Bays currently occupied are not listed.'

        if not self.fields['vehicle'].queryset.exists():
            self.fields['vehicle'].help_text = 'You need a registered vehicle before you can book.'

    def clean(self):
        cleaned = super().clean()
        # Model.clean() does the real cross-field validation (overlap, window
        # length, ownership); it needs user set, which isn't a form field.
        self.instance.user = self.user
        return cleaned

    @staticmethod
    def suggested_window():
        """Sensible defaults: from the next quarter-hour, for two hours."""
        now = timezone.localtime()
        start = (now + timedelta(minutes=15)).replace(second=0, microsecond=0)
        start = start.replace(minute=start.minute - start.minute % 15)
        return start, start + timedelta(hours=2)


class GateLookupForm(forms.Form):
    """Security's reference lookup at the gate."""

    reference = forms.CharField(
        max_length=12,
        label='Booking reference',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg text-uppercase',
            'placeholder': 'ATU-XXXXXX',
            'autofocus': 'autofocus',
        }),
    )

    def clean_reference(self):
        return self.cleaned_data['reference'].strip().upper()
