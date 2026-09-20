"""Booking lifecycle operations.

Every state change a reservation can undergo lives here rather than in the
views, so the slot-status sync and the alerts that accompany each transition
happen no matter which entry point triggers it (web view, admin action, or a
future API).
"""

from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notify
from parking.models import ParkingSlot, SlotStatusChangeLog
from parking.services import update_slot_status

from .models import Reservation


def _slot_label(reservation):
    return f'{reservation.slot} in {reservation.zone.name}'


def _release_slot_if_uncontested(reservation, actor):
    """Frees the slot unless another live booking still covers right now.

    Without this check, cancelling a booking that ends tomorrow would wrongly
    free a slot that a different booking is actively using today.
    """
    now = timezone.now()
    still_held = (
        Reservation.objects
        .filter(
            slot=reservation.slot,
            status__in=Reservation.HOLDING_STATUSES,
            start_time__lte=now,
            end_time__gte=now,
        )
        .exclude(pk=reservation.pk)
        .exists()
    )
    if not still_held and reservation.slot.status != ParkingSlot.Status.AVAILABLE:
        update_slot_status(
            reservation.slot,
            ParkingSlot.Status.AVAILABLE,
            source=SlotStatusChangeLog.Source.MANUAL,
            changed_by=actor,
        )


@transaction.atomic
def create_reservation(reservation, *, actor=None):
    """Persists a validated booking, syncs the slot, and alerts the booker."""
    reservation.status = Reservation.Status.CONFIRMED
    reservation.save()

    # Only claim the slot if the booking has already started; a booking for
    # next week must not show the bay as reserved today.
    if reservation.is_current:
        update_slot_status(
            reservation.slot,
            ParkingSlot.Status.RESERVED,
            source=SlotStatusChangeLog.Source.MANUAL,
            changed_by=actor or reservation.user,
        )

    local_start = timezone.localtime(reservation.start_time)
    local_end = timezone.localtime(reservation.end_time)
    notify(
        reservation.user,
        f'Booking {reservation.reference} confirmed — {_slot_label(reservation)}, '
        f'{local_start:%d %b %H:%M} to {local_end:%H:%M}.',
        category=Notification.Category.BOOKING,
        email_subject=f'Parking confirmed: {reservation.reference}',
        email_body=(
            f'Hello {reservation.user.get_full_name() or reservation.user.username},\n\n'
            f'Your parking slot is confirmed.\n\n'
            f'Reference:  {reservation.reference}\n'
            f'Slot:       {_slot_label(reservation)}\n'
            f'Vehicle:    {reservation.vehicle.registration_number}\n'
            f'From:       {local_start:%d %b %Y, %H:%M}\n'
            f'Until:      {local_end:%d %b %Y, %H:%M}\n\n'
            f'Show the reference above to security at the gate.\n\n'
            f'— ATU Smart Parking'
        ),
    )
    return reservation


@transaction.atomic
def cancel_reservation(reservation, *, actor=None):
    """Cancels a booking that has not yet checked in."""
    if not reservation.can_cancel:
        raise ValueError(
            f'This booking is {reservation.get_status_display().lower()} '
            f'and can no longer be cancelled.'
        )

    reservation.status = Reservation.Status.CANCELLED
    reservation.cancelled_at = timezone.now()
    reservation.save(update_fields=['status', 'cancelled_at', 'updated_at'])

    _release_slot_if_uncontested(reservation, actor or reservation.user)

    by_staff = actor is not None and actor != reservation.user
    notify(
        reservation.user,
        f'Booking {reservation.reference} was cancelled'
        f'{" by parking staff" if by_staff else ""} — {_slot_label(reservation)}.',
        category=Notification.Category.STATUS_CHANGE,
        email_subject=f'Parking cancelled: {reservation.reference}',
        email_body=(
            f'Your booking {reservation.reference} for {_slot_label(reservation)} '
            f'has been cancelled'
            f'{" by parking staff" if by_staff else ""}.\n\n'
            f'The slot is now available for others to book.\n\n'
            f'— ATU Smart Parking'
        ),
    )
    return reservation


@transaction.atomic
def check_in(reservation, *, actor):
    """Security confirms the vehicle at the gate; the slot becomes occupied."""
    if reservation.status != Reservation.Status.CONFIRMED:
        raise ValueError(f'Only confirmed bookings can be checked in (this one is {reservation.status}).')

    reservation.status = Reservation.Status.ACTIVE
    reservation.checked_in_at = timezone.now()
    reservation.save(update_fields=['status', 'checked_in_at', 'updated_at'])

    update_slot_status(
        reservation.slot,
        ParkingSlot.Status.OCCUPIED,
        source=SlotStatusChangeLog.Source.MANUAL,
        changed_by=actor,
    )

    notify(
        reservation.user,
        f'Checked in at {_slot_label(reservation)} — booking {reservation.reference} is now active.',
        category=Notification.Category.STATUS_CHANGE,
        email_subject=f'Checked in: {reservation.reference}',
        email_body=(
            f'Your vehicle {reservation.vehicle.registration_number} was verified at the gate '
            f'and your booking {reservation.reference} is now active.\n\n'
            f'Slot: {_slot_label(reservation)}\n\n'
            f'— ATU Smart Parking'
        ),
    )
    return reservation


@transaction.atomic
def check_out(reservation, *, actor):
    """Vehicle has left; the booking closes and the slot frees up."""
    if reservation.status != Reservation.Status.ACTIVE:
        raise ValueError(f'Only active bookings can be checked out (this one is {reservation.status}).')

    reservation.status = Reservation.Status.COMPLETED
    reservation.checked_out_at = timezone.now()
    reservation.save(update_fields=['status', 'checked_out_at', 'updated_at'])

    _release_slot_if_uncontested(reservation, actor)

    notify(
        reservation.user,
        f'Booking {reservation.reference} completed — thanks for using ATU Smart Parking.',
        category=Notification.Category.STATUS_CHANGE,
        email_subject=f'Parking completed: {reservation.reference}',
        email_body=(
            f'Your booking {reservation.reference} at {_slot_label(reservation)} is complete.\n\n'
            f'— ATU Smart Parking'
        ),
    )
    return reservation


def expire_lapsed(*, actor=None):
    """Closes out bookings whose window has passed without a check-out.

    Called opportunistically when reservation pages are viewed, which keeps
    the data honest without needing a scheduler in place yet. Returns the
    number of bookings expired.
    """
    now = timezone.now()
    lapsed = list(
        Reservation.objects
        .select_related('slot__zone', 'vehicle', 'user')
        .filter(status__in=Reservation.HOLDING_STATUSES, end_time__lt=now)
    )

    for reservation in lapsed:
        with transaction.atomic():
            was_active = reservation.status == Reservation.Status.ACTIVE
            reservation.status = Reservation.Status.EXPIRED
            reservation.save(update_fields=['status', 'updated_at'])
            _release_slot_if_uncontested(reservation, actor)

            notify(
                reservation.user,
                f'Booking {reservation.reference} expired — its window ended '
                f'{"without a check-out" if was_active else "without a check-in"}.',
                category=Notification.Category.STATUS_CHANGE,
                email_subject=f'Parking expired: {reservation.reference}',
                email_body=(
                    f'Your booking {reservation.reference} for {_slot_label(reservation)} '
                    f'has expired because its window ended.\n\n'
                    f'— ATU Smart Parking'
                ),
            )

    return len(lapsed)
