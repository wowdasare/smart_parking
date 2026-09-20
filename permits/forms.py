from datetime import timedelta

from django import forms
from django.utils import timezone

from accounts.forms import BootstrapFormMixin
from parking.models import Zone

from .models import Permit

# How long each permit type runs for by default, so applicants aren't left
# guessing at sensible dates. They can still edit both ends.
DEFAULT_TERM_DAYS = {
    Permit.PermitType.STUDENT: 120,
    Permit.PermitType.STAFF: 365,
    Permit.PermitType.VISITOR: 3,
    Permit.PermitType.CONTRACTOR: 90,
}


class PermitApplicationForm(BootstrapFormMixin, forms.ModelForm):
    """Applicant-facing form. The holder comes from the session, never the
    POST payload, so nobody can file an application in someone else's name.
    """

    class Meta:
        model = Permit
        fields = ('vehicle', 'permit_type', 'zone', 'valid_from', 'valid_until',
                  'applicant_note', 'document')
        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'valid_until': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'applicant_note': forms.TextInput(),
        }
        labels = {
            'vehicle': 'Which vehicle?',
            'permit_type': 'Permit type',
            'zone': 'Preferred zone',
            'valid_from': 'Cover from',
            'valid_until': 'Cover until',
            'applicant_note': 'Note for the parking office (optional)',
            'document': 'Supporting document (optional)',
        }

    def __init__(self, *args, holder=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.holder = holder

        self.fields['vehicle'].queryset = holder.vehicles.all()
        self.fields['vehicle'].empty_label = 'Select a vehicle'
        self.fields['zone'].queryset = Zone.objects.all()
        self.fields['zone'].empty_label = 'Any zone'
        self.fields['zone'].required = False

        if not self.fields['vehicle'].queryset.exists():
            self.fields['vehicle'].help_text = 'You need a registered vehicle before you can apply.'

    def clean(self):
        cleaned = super().clean()
        # Model.clean() owns the real rules (date order, ownership, existing
        # cover); it needs holder set, which isn't a form field.
        self.instance.holder = self.holder
        return cleaned

    @staticmethod
    def suggested_dates(permit_type=Permit.PermitType.STUDENT):
        start = timezone.localdate()
        return start, start + timedelta(days=DEFAULT_TERM_DAYS[permit_type])


class PermitReviewForm(BootstrapFormMixin, forms.Form):
    """Staff decision, with a reason the applicant will see."""

    note = forms.CharField(
        max_length=255,
        required=False,
        label='Note to the applicant',
        widget=forms.TextInput(attrs={'placeholder': 'Optional for approval, expected for rejection'}),
    )


class PlateCheckForm(forms.Form):
    """Gate-side plate lookup against active permits."""

    plate = forms.CharField(
        max_length=20,
        label='Vehicle plate',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg text-uppercase',
            'placeholder': 'GR-1234',
        }),
    )

    def clean_plate(self):
        return self.cleaned_data['plate'].strip().upper()
