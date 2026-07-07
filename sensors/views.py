from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from parking.models import ParkingSlot, Zone
from parking.services import update_slot_status

from .authentication import SensorDeviceAuthentication
from .models import SensorDevice
from .serializers import GateEventSerializer, SlotStatusReportSerializer
from .services import record_gate_event


class SlotStatusReportView(APIView):
    authentication_classes = [SensorDeviceAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, slot_id):
        serializer = SlotStatusReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        device = request.user  # SensorDevice, set by SensorDeviceAuthentication
        if data['device_id'] != device.device_id:
            return Response(
                {'detail': 'device_id in the request body does not match the authenticated device.'},
                status=400,
            )

        slot = get_object_or_404(ParkingSlot, pk=slot_id)

        if device.device_type != SensorDevice.DeviceType.SLOT_SENSOR:
            return Response({'detail': 'This device is not registered as a slot sensor.'}, status=403)
        if device.slot_id != slot.pk:
            return Response({'detail': 'This device is not assigned to this slot.'}, status=403)

        slot, applied = update_slot_status(slot, data['status'], source='sensor', device=device)

        if not applied:
            return Response(
                {
                    'detail': 'Rejected: a manual override is active for this slot.',
                    'slot': str(slot),
                    'status': slot.status,
                },
                status=409,
            )

        return Response({
            'slot': str(slot),
            'status': slot.status,
            'status_changed_at': slot.status_changed_at,
        })


class GateEventView(APIView):
    authentication_classes = [SensorDeviceAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, zone_id):
        serializer = GateEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        device = request.user
        if data['device_id'] != device.device_id:
            return Response(
                {'detail': 'device_id in the request body does not match the authenticated device.'},
                status=400,
            )

        zone = get_object_or_404(Zone, pk=zone_id)

        if device.device_type != SensorDevice.DeviceType.GATE_SENSOR:
            return Response({'detail': 'This device is not registered as a gate sensor.'}, status=403)
        if device.zone_id != zone.pk:
            return Response({'detail': 'This device is not assigned to this zone.'}, status=403)

        record_gate_event(device, zone, data['event_type'], data.get('plate_number', ''))

        return Response({
            'zone': str(zone),
            'event_type': data['event_type'],
            'current_occupancy': zone.current_occupancy,
            'capacity': zone.capacity,
        })
