"""Permit lifecycle operations.

An application moves PENDING -> ACTIVE (approved) or REJECTED, and an active
permit can later be REVOKED or EXPIRED. Every transition lives here so the
permit number assignment and the applicant alerts happen the same way
whichever entry point triggers them.
"""

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notify

from .models import Permit


def next_permit_number(*, today=None):
    """Sequential number within the calendar year, e.g. ATU-P-2026-0007.

    Derived from the highest existing number for the year rather than a
    counter table: there is exactly one writer path (approval, inside a
    transaction), and it stays correct if rows are ever imported by hand.
    """
    today = today or timezone.localdate()
    prefix = f'ATU-P-{today.year}-'
    highest = (
        Permit.objects
        .filter(permit_number__startswith=prefix)
        .aggregate(top=Max('permit_number'))['top']
    )
    sequence = int(highest.rsplit('-', 1)[1]) + 1 if highest else 1
    return f'{prefix}{sequence:04d}'


def _describe(permit):
    return (
        f'{permit.get_permit_type_display()} permit for '
        f'{permit.vehicle.registration_number} ({permit.zone_label})'
    )


@transaction.atomic
def submit_application(permit, *, actor=None):
    """Records a new application and tells the applicant it's in the queue."""
    permit.status = Permit.Status.PENDING
    if not permit.fee_amount:
        permit.fee_amount = Permit.DEFAULT_FEES.get(permit.permit_type, 0)
    permit.save()

    notify(
        permit.holder,
        f'Permit application received for {permit.vehicle.registration_number} — '
        f'awaiting review by the parking office.',
        category=Notification.Category.SYSTEM,
        email_subject='Permit application received',
        email_body=(
            f'Hello {permit.holder.get_full_name() or permit.holder.username},\n\n'
            f'We have received your application for a {_describe(permit)}.\n\n'
            f'Requested cover: {permit.valid_from:%d %b %Y} to {permit.valid_until:%d %b %Y}\n'
            f'Fee:             GHS {permit.fee_amount}\n\n'
            f'The parking office will review it and you will be notified of the outcome.\n\n'
            f'— ATU Smart Parking'
        ),
    )
    return permit


@transaction.atomic
def approve(permit, *, reviewer, note=''):
    """Approves an application and issues its permit number."""
    if not permit.can_be_reviewed:
        raise ValueError(
            f'This permit is {permit.get_status_display().lower()} and can no longer be reviewed.'
        )

    permit.status = Permit.Status.ACTIVE
    permit.permit_number = next_permit_number()
    permit.reviewed_by = reviewer
    permit.reviewed_at = timezone.now()
    permit.review_note = note
    permit.save(update_fields=[
        'status', 'permit_number', 'reviewed_by', 'reviewed_at', 'review_note', 'updated_at',
    ])

    notify(
        permit.holder,
        f'Permit {permit.permit_number} approved — valid until '
        f'{permit.valid_until:%d %b %Y}.',
        category=Notification.Category.STATUS_CHANGE,
        email_subject=f'Permit approved: {permit.permit_number}',
        email_body=(
            f'Good news — your {_describe(permit)} has been approved.\n\n'
            f'Permit number: {permit.permit_number}\n'
            f'Valid:         {permit.valid_from:%d %b %Y} to {permit.valid_until:%d %b %Y}\n'
            f'Zone:          {permit.zone_label}\n'
            f'Fee:           GHS {permit.fee_amount}'
            f'{" (paid)" if permit.is_paid else " — payable at the parking office"}\n\n'
            f'{note or ""}\n\n'
            f'— ATU Smart Parking'
        ).replace('\n\n\n\n', '\n\n'),
    )
    return permit


@transaction.atomic
def reject(permit, *, reviewer, note=''):
    """Declines an application, passing the reason back to the applicant."""
    if not permit.can_be_reviewed:
        raise ValueError(
            f'This permit is {permit.get_status_display().lower()} and can no longer be reviewed.'
        )

    permit.status = Permit.Status.REJECTED
    permit.reviewed_by = reviewer
    permit.reviewed_at = timezone.now()
    permit.review_note = note
    permit.save(update_fields=[
        'status', 'reviewed_by', 'reviewed_at', 'review_note', 'updated_at',
    ])

    notify(
        permit.holder,
        f'Permit application for {permit.vehicle.registration_number} was not approved'
        f'{f" — {note}" if note else "."}',
        category=Notification.Category.STATUS_CHANGE,
        email_subject='Permit application declined',
        email_body=(
            f'Your application for a {_describe(permit)} was not approved.\n\n'
            f'{f"Reason: {note}" if note else "No reason was recorded."}\n\n'
            f'You may correct the details and apply again, or contact the parking '
            f'office if you believe this is a mistake.\n\n'
            f'— ATU Smart Parking'
        ),
    )
    return permit


@transaction.atomic
def revoke(permit, *, actor, note=''):
    """Withdraws cover from an already-active permit."""
    if not permit.can_be_revoked:
        raise ValueError(f'Only an active permit can be revoked (this one is {permit.status}).')

    permit.status = Permit.Status.REVOKED
    permit.review_note = note
    permit.reviewed_by = actor
    permit.reviewed_at = timezone.now()
    permit.save(update_fields=[
        'status', 'review_note', 'reviewed_by', 'reviewed_at', 'updated_at',
    ])

    notify(
        permit.holder,
        f'Permit {permit.permit_number or ""} has been revoked'
        f'{f" — {note}" if note else "."}'.strip(),
        category=Notification.Category.STATUS_CHANGE,
        email_subject='Permit revoked',
        email_body=(
            f'Your {_describe(permit)} has been revoked with immediate effect.\n\n'
            f'{f"Reason: {note}" if note else ""}\n\n'
            f'Parking on campus with this vehicle is no longer covered. Contact the '
            f'parking office if you need to discuss this.\n\n'
            f'— ATU Smart Parking'
        ),
    )
    return permit


@transaction.atomic
def withdraw(permit, *, actor):
    """The applicant pulls their own pending application."""
    if not permit.can_be_withdrawn:
        raise ValueError(
            f'This permit is {permit.get_status_display().lower()} and can no longer be withdrawn.'
        )

    permit.status = Permit.Status.REJECTED
    permit.review_note = 'Withdrawn by the applicant.'
    permit.reviewed_at = timezone.now()
    permit.save(update_fields=['status', 'review_note', 'reviewed_at', 'updated_at'])
    return permit


@transaction.atomic
def mark_paid(permit, *, actor):
    """Records the fee as settled at the parking office."""
    if permit.is_paid:
        return permit

    permit.is_paid = True
    permit.save(update_fields=['is_paid', 'updated_at'])

    notify(
        permit.holder,
        f'Payment of GHS {permit.fee_amount} received for permit '
        f'{permit.permit_number or permit.vehicle.registration_number}.',
        category=Notification.Category.SYSTEM,
        email_subject='Permit payment received',
        email_body=(
            f'We have recorded your payment of GHS {permit.fee_amount} for '
            f'{_describe(permit)}.\n\n— ATU Smart Parking'
        ),
    )
    return permit


def expire_lapsed(*, actor=None):
    """Moves active permits past their end date to EXPIRED.

    Called when permit pages are viewed, so statuses stay honest without a
    scheduler. Returns the number expired.
    """
    today = timezone.localdate()
    lapsed = list(
        Permit.objects
        .select_related('holder', 'vehicle', 'zone')
        .filter(status=Permit.Status.ACTIVE, valid_until__lt=today)
    )

    for permit in lapsed:
        with transaction.atomic():
            permit.status = Permit.Status.EXPIRED
            permit.save(update_fields=['status', 'updated_at'])

            notify(
                permit.holder,
                f'Permit {permit.permit_number or ""} expired on '
                f'{permit.valid_until:%d %b %Y}. Apply again to keep parking on campus.'.strip(),
                category=Notification.Category.STATUS_CHANGE,
                email_subject='Permit expired',
                email_body=(
                    f'Your {_describe(permit)} expired on '
                    f'{permit.valid_until:%d %b %Y}.\n\n'
                    f'Apply for a new permit to continue parking on campus.\n\n'
                    f'— ATU Smart Parking'
                ),
            )

    return len(lapsed)


def permit_for_plate(plate_number):
    """The current permit covering a plate, or None.

    This is the gate's cross-check: the sensor API already stores
    GateEvent.plate_number, and this turns that raw string into an answer.
    """
    return (
        Permit.objects
        .active()
        .for_plate(plate_number)
        .select_related('holder', 'vehicle', 'zone')
        .first()
    )
