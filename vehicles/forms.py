from django import forms

from accounts.forms import BootstrapFormMixin

from .models import Vehicle


class VehicleForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ('registration_number', 'vehicle_type', 'make', 'model', 'color')

    def clean_registration_number(self):
        return self.cleaned_data['registration_number'].upper().strip()
