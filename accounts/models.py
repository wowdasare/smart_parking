from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model for ATU Smart Parking.

    Extends Django's AbstractUser (keeps username/email/password, permissions,
    and admin/auth integration) and adds a role field used for access control
    across the platform, plus basic contact info for profile management.
    """

    class Role(models.TextChoices):
        STUDENT = 'student', 'Student'
        STAFF = 'staff', 'Staff'
        GUEST = 'guest', 'Guest'
        ADMIN = 'admin', 'Admin'
        SECURITY = 'security', 'Security'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )
    phone_number = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_security(self):
        return self.role == self.Role.SECURITY

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN
