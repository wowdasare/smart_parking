from rest_framework import serializers

from parking.models import ParkingSlot

from .models import GateEvent

# Sensors physically detect occupancy — they can't decide "reserved", that's
# a booking-flow decision. Restrict reportable values accordingly.
SENSOR_REPORTABLE_STATUSES = (ParkingSlot.Status.AVAILABLE, ParkingSlot.Status.OCCUPIED)


class SlotStatusReportSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SENSOR_REPORTABLE_STATUSES)
    device_id = serializers.CharField(max_length=64)
    timestamp = serializers.DateTimeField(required=False)


class GateEventSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=GateEvent.EventType.choices)
    device_id = serializers.CharField(max_length=64)
    timestamp = serializers.DateTimeField(required=False)
    # Optional and unused beyond storage for now — reserved for future
    # license-plate-based permit cross-checking.
    plate_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
