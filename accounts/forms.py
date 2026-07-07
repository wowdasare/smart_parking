from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserChangeForm,
    UserCreationForm,
)
from django.forms.widgets import CheckboxInput

from .models import User


class BootstrapFormMixin:
    """Adds Bootstrap 5 form-control/form-check-input classes to every field.

    Lets us use Django's built-in auth forms (login, password reset, etc.)
    as-is while still matching the rest of the Bootstrap-styled UI.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = 'form-check-input' if isinstance(field.widget, CheckboxInput) else 'form-control'
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} {css_class}'.strip()


class UserRegistrationForm(BootstrapFormMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'phone_number')


class UserProfileForm(BootstrapFormMixin, UserChangeForm):
    password = None  # hide the password hash field; password changes go through a dedicated flow

    class Meta(UserChangeForm.Meta):
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone_number')


class StyledAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    pass


class StyledPasswordResetForm(BootstrapFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(BootstrapFormMixin, SetPasswordForm):
    pass


class StyledPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    pass
