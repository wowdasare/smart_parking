from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import SensorDevice


class SensorDeviceAuthentication(BaseAuthentication):
    """Authenticates a device via `Authorization: Api-Key <key>`.

    Devices aren't Django Users — there's no login/password for hardware.
    On success, request.user is the SensorDevice instance (it duck-types
    is_authenticated) and request.auth is the raw key.
    """

    keyword = 'Api-Key'

    def authenticate(self, request):
        header = request.headers.get('Authorization', '')
        parts = header.split()

        if not parts or parts[0] != self.keyword:
            return None  # let other authenticators (or AllowAny) handle it

        if len(parts) != 2:
            raise AuthenticationFailed('Authorization header must be "Api-Key <key>".')

        key = parts[1]
        try:
            device = SensorDevice.objects.get(api_key=key)
        except SensorDevice.DoesNotExist:
            raise AuthenticationFailed('Invalid API key.')

        if not device.is_active:
            raise AuthenticationFailed('This device has been deactivated.')

        device.last_seen_at = timezone.now()
        device.save(update_fields=['last_seen_at'])

        return (device, key)
