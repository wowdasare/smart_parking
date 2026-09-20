from datetime import timedelta
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from accounts.models import User
from notifications.models import Notification
from parking.models import ParkingSlot, SlotStatusChangeLog, Zone
from permits.models import Permit
from permits.services import expire_lapsed as expire_lapsed_permits
from reservations.models import Reservation
from reservations.services import expire_lapsed
from sensors.models import GateEvent, SensorDevice
from vehicles.models import Vehicle

# A device that hasn't checked in for this long is treated as offline on the
# dashboards. Sensors are expected to report well inside this window, so a
# stale timestamp means a dead battery or dropped WiFi, not idleness.
DEVICE_STALE_MINUTES = 15


def admin_required(view_func):
    """Anonymous users get the login redirect; signed-in non-admins get a 403
    rather than being bounced to a login form they're already past.
    """

    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied('Administrator access is required for this page.')
        return view_func(request, *args, **kwargs)

    return _wrapped


# --------------------------------------------------------------------------
# Shared aggregate helpers
# --------------------------------------------------------------------------

def _slot_breakdown():
    """Slot counts per status, with every status present even at zero so
    templates never have to guard for missing keys.
    """
    counts = {value: 0 for value, _ in ParkingSlot.Status.choices}
    for row in ParkingSlot.objects.values('status').annotate(n=Count('id')):
        counts[row['status']] = row['n']

    total = sum(counts.values())
    breakdown = {
        'available': counts[ParkingSlot.Status.AVAILABLE],
        'occupied': counts[ParkingSlot.Status.OCCUPIED],
        'reserved': counts[ParkingSlot.Status.RESERVED],
        'total': total,
    }
    # Percentages drive the stacked bar widths; guard against 0 slots.
    for key in ('available', 'occupied', 'reserved'):
        breakdown[f'{key}_pct'] = round(breakdown[key] / total * 100) if total else 0
    return breakdown


def _zone_rows():
    """Per-zone occupancy with a pre-computed bar width and severity class.

    Zone.capacity is nullable and occupancy is gate-counted, so a zone can
    legitimately have no percentage at all — the template shows a raw count
    in that case instead of a misleading full/empty bar.
    """
    rows = []
    zones = Zone.objects.prefetch_related('slots').annotate(slot_total=Count('slots'))
    for zone in zones:
        capacity = zone.capacity or 0
        occupancy = zone.current_occupancy
        percent = min(round(occupancy / capacity * 100), 100) if capacity else None

        if percent is None:
            level = 'occ-low'
        elif percent >= 90:
            level = 'occ-high'
        elif percent >= 60:
            level = 'occ-mid'
        else:
            level = 'occ-low'

        rows.append({
            'zone': zone,
            'occupancy': occupancy,
            'capacity': zone.capacity,
            'percent': percent,
            'level': level,
            'free': max(capacity - occupancy, 0) if capacity else None,
            'is_full': bool(capacity) and occupancy >= capacity,
            'slots': list(zone.slots.all()),
            'slot_total': zone.slot_total,
        })
    return rows


def _campus_totals(zone_rows):
    """Campus-wide occupancy across zones that actually declare a capacity."""
    capacity = sum(r['capacity'] for r in zone_rows if r['capacity'])
    occupancy = sum(r['occupancy'] for r in zone_rows if r['capacity'])
    percent = round(occupancy / capacity * 100) if capacity else 0
    return {
        'capacity': capacity,
        'occupancy': occupancy,
        'percent': percent,
        'free': max(capacity - occupancy, 0),
        'zones_open': sum(1 for r in zone_rows if not r['is_full']),
        'zone_count': len(zone_rows),
    }


def _device_rows():
    """Sensor fleet with an online/idle/offline verdict per device."""
    cutoff = timezone.now() - timedelta(minutes=DEVICE_STALE_MINUTES)
    rows = []
    for device in SensorDevice.objects.select_related('slot__zone', 'zone').order_by('device_id'):
        if not device.is_active:
            state, label = 'is-off', 'Disabled'
        elif device.last_seen_at is None:
            state, label = 'is-idle', 'Never reported'
        elif device.last_seen_at < cutoff:
            state, label = 'is-off', 'Offline'
        else:
            state, label = 'is-on', 'Online'

        rows.append({'device': device, 'state': state, 'label': label})
    return rows


def _slot_activity(limit=6):
    """Recent slot status changes, shaped for the timeline component."""
    logs = (
        SlotStatusChangeLog.objects
        .select_related('slot__zone', 'changed_by')
        .all()[:limit]
    )
    tone_by_status = {
        ParkingSlot.Status.AVAILABLE: 'tl-green',
        ParkingSlot.Status.OCCUPIED: 'tl-red',
        ParkingSlot.Status.RESERVED: 'tl-gold',
    }
    rows = []
    for log in logs:
        rows.append({
            'log': log,
            'tone': 'tl-muted' if not log.applied else tone_by_status.get(log.attempted_status, 'tl-blue'),
            'actor': log.changed_by.get_full_name() or log.changed_by.username if log.changed_by else (log.device_id or 'system'),
        })
    return rows


# --------------------------------------------------------------------------
# Role dashboards
# --------------------------------------------------------------------------

@login_required
def home(request):
    if request.user.role == User.Role.ADMIN:
        return _admin_dashboard(request)
    if request.user.role == User.Role.SECURITY:
        return _security_dashboard(request)
    return _user_dashboard(request)


def _admin_dashboard(request):
    expire_lapsed()
    expire_lapsed_permits()
    zone_rows = _zone_rows()
    totals = _campus_totals(zone_rows)
    slots = _slot_breakdown()
    devices = _device_rows()

    role_counts = {row['role']: row['n'] for row in User.objects.values('role').annotate(n=Count('id'))}
    role_rows = [
        {'label': label, 'count': role_counts.get(value, 0)}
        for value, label in User.Role.choices
    ]

    today = timezone.localdate()
    events_today = GateEvent.objects.filter(recorded_at__date=today)

    context = {
        'permits_pending': Permit.objects.awaiting_review().count(),
        'permits_active': Permit.objects.active().count(),
        'permits_unpaid': Permit.objects.filter(is_paid=False).exclude(
            status__in=(Permit.Status.REJECTED, Permit.Status.REVOKED)
        ).count(),
        'pending_permits': (
            Permit.objects
            .awaiting_review()
            .select_related('holder', 'vehicle', 'zone')
            .order_by('created_at')[:6]
        ),
        'live_bookings': Reservation.objects.filter(status__in=Reservation.HOLDING_STATUSES).count(),
        'bookings_today': Reservation.objects.filter(start_time__date=today).count(),
        'total_bookings': Reservation.objects.count(),
        'recent_bookings': (
            Reservation.objects
            .select_related('slot__zone', 'vehicle', 'user')
            .order_by('-created_at')[:6]
        ),
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'total_vehicles': Vehicle.objects.count(),
        'vehicles_added_week': Vehicle.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
        'role_rows': role_rows,
        'zone_rows': zone_rows,
        'totals': totals,
        'slots': slots,
        'devices': devices,
        'devices_offline': sum(1 for d in devices if d['state'] == 'is-off'),
        'entries_today': events_today.filter(event_type=GateEvent.EventType.ENTRY).count(),
        'exits_today': events_today.filter(event_type=GateEvent.EventType.EXIT).count(),
        'activity': _slot_activity(),
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


def _security_dashboard(request):
    expire_lapsed()
    expire_lapsed_permits()
    now = timezone.now()
    zone_rows = _zone_rows()
    totals = _campus_totals(zone_rows)
    slots = _slot_breakdown()
    devices = _device_rows()

    today = timezone.localdate()
    events_today = GateEvent.objects.filter(recorded_at__date=today)

    context = {
        'permits_active': Permit.objects.active().count(),
        'permits_expiring': [
            p for p in Permit.objects.active().select_related('holder', 'vehicle')
            if p.expires_soon
        ],
        'expected_now': (
            Reservation.objects
            .select_related('slot__zone', 'vehicle', 'user')
            .filter(status=Reservation.Status.CONFIRMED, start_time__lte=now, end_time__gte=now)
            .order_by('start_time')[:8]
        ),
        'on_site': (
            Reservation.objects
            .select_related('slot__zone', 'vehicle', 'user')
            .filter(status=Reservation.Status.ACTIVE)
            .order_by('checked_in_at')[:8]
        ),
        'confirmed_today': Reservation.objects.filter(
            start_time__date=today, status__in=Reservation.HOLDING_STATUSES
        ).count(),
        'on_campus': Zone.objects.aggregate(total=Sum('current_occupancy'))['total'] or 0,
        'entries_today': events_today.filter(event_type=GateEvent.EventType.ENTRY).count(),
        'exits_today': events_today.filter(event_type=GateEvent.EventType.EXIT).count(),
        'zone_rows': zone_rows,
        'totals': totals,
        'slots': slots,
        'devices': devices,
        'devices_offline': sum(1 for d in devices if d['state'] == 'is-off'),
        'recent_events': GateEvent.objects.select_related('zone', 'device')[:8],
        'zones_full': [r for r in zone_rows if r['is_full']],
        'activity': _slot_activity(),
    }
    return render(request, 'dashboard/security_dashboard.html', context)


def _user_dashboard(request):
    expire_lapsed()
    expire_lapsed_permits()
    zone_rows = _zone_rows()
    totals = _campus_totals(zone_rows)
    slots = _slot_breakdown()

    my_reservations = Reservation.objects.filter(user=request.user).select_related('slot__zone', 'vehicle')

    my_permits = Permit.objects.filter(holder=request.user).select_related('vehicle', 'zone')
    current_permit = next((p for p in my_permits if p.is_current), None)

    context = {
        'my_permits': my_permits,
        'current_permit': current_permit,
        'permit_pending': my_permits.filter(status=Permit.Status.PENDING).exists(),
        'live_bookings': my_reservations.filter(status__in=Reservation.HOLDING_STATUSES).count(),
        'upcoming_bookings': (
            my_reservations
            .filter(status__in=Reservation.HOLDING_STATUSES, end_time__gte=timezone.now())
            .order_by('start_time')[:5]
        ),
        'vehicles': request.user.vehicles.all(),
        'vehicle_count': request.user.vehicles.count(),
        'unread_notifications': Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count(),
        'recent_notifications': Notification.objects.filter(recipient=request.user)[:5],
        'zone_rows': zone_rows,
        'totals': totals,
        'slots': slots,
    }
    return render(request, 'dashboard/user_dashboard.html', context)


# --------------------------------------------------------------------------
# In-app management screens (admin only)
# --------------------------------------------------------------------------

@admin_required
def manage_users(request):
    query = request.GET.get('q', '').strip()
    role = request.GET.get('role', '').strip()

    users = User.objects.annotate(vehicle_total=Count('vehicles')).order_by('username')
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    if role:
        users = users.filter(role=role)

    page = Paginator(users, 20).get_page(request.GET.get('page'))
    context = {
        'page_obj': page,
        'query': query,
        'role': role,
        'role_choices': User.Role.choices,
        'total_count': users.count(),
    }
    return render(request, 'dashboard/manage_users.html', context)


@admin_required
def manage_vehicles(request):
    query = request.GET.get('q', '').strip()
    vehicle_type = request.GET.get('type', '').strip()

    vehicles = Vehicle.objects.select_related('owner').order_by('registration_number')
    if query:
        vehicles = vehicles.filter(
            Q(registration_number__icontains=query)
            | Q(make__icontains=query)
            | Q(model__icontains=query)
            | Q(owner__username__icontains=query)
        )
    if vehicle_type:
        vehicles = vehicles.filter(vehicle_type=vehicle_type)

    page = Paginator(vehicles, 20).get_page(request.GET.get('page'))
    context = {
        'page_obj': page,
        'query': query,
        'vehicle_type': vehicle_type,
        'type_choices': Vehicle.VehicleType.choices,
        'total_count': vehicles.count(),
    }
    return render(request, 'dashboard/manage_vehicles.html', context)


@admin_required
def manage_zones(request):
    zone_rows = _zone_rows()
    context = {
        'zone_rows': zone_rows,
        'totals': _campus_totals(zone_rows),
        'slots': _slot_breakdown(),
        'devices': _device_rows(),
        'activity': _slot_activity(limit=10),
    }
    return render(request, 'dashboard/manage_zones.html', context)
