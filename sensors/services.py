from parking.models import Zone
from parking.services import adjust_zone_occupancy

from .models import GateEvent, SensorDevice


def record_gate_event(device: SensorDevice, zone: Zone, event_type: str, plate_number: str = '') -> GateEvent:
    """Logs the raw event, then delegates the zone-level counter update to
    parking.services — sensors knows about parking, not the other way
    around, so parking stays free of any dependency on how the count fed in.
    """
    event = GateEvent.objects.create(
        zone=zone,
        device=device,
        event_type=event_type,
        plate_number=plate_number,
    )
    adjust_zone_occupancy(zone, event_type)
    return event
