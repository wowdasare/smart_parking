from django.conf import settings
from django.core.mail import send_mail

from .models import Notification


def notify(recipient, message, *, category=Notification.Category.SYSTEM, email_subject=None, email_body=None):
    """Creates the on-site alert and, when the user has an email address,
    sends the matching email.

    Email failures are swallowed deliberately: a booking must not fail
    because SMTP is unreachable. The Notification row is the source of
    truth, and it is written first for exactly that reason.
    """
    notification = Notification.objects.create(
        recipient=recipient,
        category=category,
        message=message,
    )

    if email_subject and recipient.email:
        send_mail(
            subject=email_subject,
            message=email_body or message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient.email],
            fail_silently=True,
        )

    return notification


def mark_all_read(user):
    return Notification.objects.filter(recipient=user, is_read=False).update(is_read=True)
