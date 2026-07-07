from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import ParkingSlot, SlotStatusChangeLog, Zone


def update_slot_status(slot: ParkingSlot, new_status: str, *, source: str, device=None, changed_by=None) -> tuple[ParkingSlot, bool]:
    """Single entry point for changing a slot's status — sensor reports and
    a future manual-update view (e.g. security dashboard) both call this, so
    conflict resolution and audit logging only live in one place.

    source: SlotStatusChangeLog.Source.SENSOR or .MANUAL.
    device: the reporting SensorDevice, for logging (source=sensor only).
    changed_by: the acting User, for logging (source=manual only).

    Returns (slot, applied) — applied is False when a sensor report was
    rejected because a manual override is still within its grace period.

    Django admin's own manual-edit path does NOT use this function — see
    ParkingSlotAdmin.save_model for why.
    """
    previous_status = slot.status

    if source == SlotStatusChangeLog.Source.SENSOR and slot.manual_override_at:
        grace_until = slot.manual_override_at + timedelta(minutes=settings.MANUAL_OVERRIDE_GRACE_MINUTES)
        if timezone.now() < grace_until and previous_status != new_status:
            SlotStatusChangeLog.objects.create(
                slot=slot,
                source=SlotStatusChangeLog.Source.SENSOR,
                device_id=device.device_id if device else '',
                previous_status=previous_status,
                attempted_status=new_status,
                applied=False,
            )
            return slot, False

    if previous_status == new_status:
        return slot, True  # already in the requested state — nothing to apply or log

    slot.status = new_status
    update_fields = ['status', 'status_changed_at']
    if source == SlotStatusChangeLog.Source.MANUAL:
        slot.manual_override_at = timezone.now()
        update_fields.append('manual_override_at')
    slot.save(update_fields=update_fields)

    SlotStatusChangeLog.objects.create(
        slot=slot,
        source=source,
        device_id=device.device_id if (source == SlotStatusChangeLog.Source.SENSOR and device) else '',
        changed_by=changed_by if source == SlotStatusChangeLog.Source.MANUAL else None,
        previous_status=previous_status,
        attempted_status=new_status,
        applied=True,
    )
    return slot, True


def log_manual_status_change(slot: ParkingSlot, previous_status: str, changed_by) -> None:
    """Records a manual status change that the caller has already persisted
    (Django admin's save_model mutates its instance before we ever see it,
    so it can't go through update_slot_status's before/after comparison —
    this is the equivalent bookkeeping for that path specifically).
    """
    if previous_status == slot.status:
        return
    SlotStatusChangeLog.objects.create(
        slot=slot,
        source=SlotStatusChangeLog.Source.MANUAL,
        changed_by=changed_by,
        previous_status=previous_status,
        attempted_status=slot.status,
        applied=True,
    )


def adjust_zone_occupancy(zone: Zone, event_type: str) -> Zone:
    """Adjusts a zone's gate-counted occupancy. Floors at 0 so a stray/
    duplicate exit event can't push the count negative; caps at capacity
    (when known) so a stray entry can't overshoot it.
    """
    if event_type == 'entry':
        zone.current_occupancy += 1
        if zone.capacity is not None:
            zone.current_occupancy = min(zone.current_occupancy, zone.capacity)
    elif event_type == 'exit':
        zone.current_occupancy = max(zone.current_occupancy - 1, 0)
    zone.save(update_fields=['current_occupancy'])
    return zone
