from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from permits.services import permit_for_plate

from . import services
from .forms import GateLookupForm, ReservationForm
from .models import Reservation


def _is_gate_staff(user):
    """Security and admins act on other people's bookings at the gate."""
    return user.is_superuser or user.role in (User.Role.SECURITY, User.Role.ADMIN)


def _visible_reservations(user):
    """Gate staff see every booking; everyone else sees only their own."""
    queryset = Reservation.objects.select_related('slot__zone', 'vehicle', 'user')
    if _is_gate_staff(user):
        return queryset
    return queryset.filter(user=user)


@login_required
def reservation_list(request):
    # Closing out lapsed bookings here keeps statuses honest without a
    # scheduler; it's a cheap no-op once everything is already settled.
    services.expire_lapsed()

    reservations = _visible_reservations(request.user)
    now = timezone.now()

    upcoming = [r for r in reservations if r.is_holding and r.end_time >= now]
    history = [r for r in reservations if not (r.is_holding and r.end_time >= now)]

    context = {
        'upcoming': upcoming,
        'history': history,
        'is_gate_staff': _is_gate_staff(request.user),
        'can_book': request.user.vehicles.exists(),
    }
    return render(request, 'reservations/reservation_list.html', context)


@login_required
def reservation_create(request):
    if request.method == 'POST':
        form = ReservationForm(request.POST, user=request.user)
        if form.is_valid():
            reservation = services.create_reservation(form.instance, actor=request.user)
            messages.success(
                request,
                f'Booking confirmed. Your gate reference is {reservation.reference}.',
            )
            return redirect('reservations:detail', pk=reservation.pk)
    else:
        start, end = ReservationForm.suggested_window()
        form = ReservationForm(user=request.user, initial={'start_time': start, 'end_time': end})

    return render(request, 'reservations/reservation_form.html', {
        'form': form,
        'has_vehicles': request.user.vehicles.exists(),
    })


@login_required
def reservation_detail(request, pk):
    reservation = get_object_or_404(_visible_reservations(request.user), pk=pk)
    return render(request, 'reservations/reservation_detail.html', {
        'reservation': reservation,
        'is_gate_staff': _is_gate_staff(request.user),
    })


@login_required
def reservation_cancel(request, pk):
    reservation = get_object_or_404(_visible_reservations(request.user), pk=pk)

    if request.method == 'POST':
        try:
            services.cancel_reservation(reservation, actor=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Booking {reservation.reference} cancelled.')
        return redirect('reservations:list')

    return render(request, 'reservations/reservation_confirm_cancel.html', {'reservation': reservation})


# --------------------------------------------------------------------------
# Gate verification (security / admin)
# --------------------------------------------------------------------------

@login_required
def gate_verify(request):
    """Look a booking up by reference, then check the vehicle in or out."""
    if not _is_gate_staff(request.user):
        raise PermissionDenied('Gate verification is limited to security staff.')

    services.expire_lapsed(actor=request.user)

    reservation = None
    form = GateLookupForm(request.GET or None)
    if form.is_valid():
        reference = form.cleaned_data['reference']
        reservation = (
            Reservation.objects
            .select_related('slot__zone', 'vehicle', 'user')
            .filter(reference=reference)
            .first()
        )
        if reservation is None:
            messages.error(request, f'No booking found with reference {reference}.')

    now = timezone.now()
    context = {
        'form': form,
        'reservation': reservation,
        # The permit answers "may this vehicle be on campus at all?", which is
        # a separate question from "does it hold this bay right now?" — a
        # booking can be valid while its permit has lapsed, so security needs
        # both answers on one screen.
        'permit': permit_for_plate(reservation.vehicle.registration_number) if reservation else None,
        'expected_now': (
            Reservation.objects
            .select_related('slot__zone', 'vehicle', 'user')
            .filter(status=Reservation.Status.CONFIRMED, start_time__lte=now, end_time__gte=now)
            .order_by('start_time')
        ),
        'on_site': (
            Reservation.objects
            .select_related('slot__zone', 'vehicle', 'user')
            .filter(status=Reservation.Status.ACTIVE)
            .order_by('checked_in_at')
        ),
    }
    return render(request, 'reservations/gate_verify.html', context)


@login_required
def gate_action(request, pk):
    """Applies a check-in or check-out to a booking. POST only."""
    if not _is_gate_staff(request.user):
        raise PermissionDenied('Gate verification is limited to security staff.')

    reservation = get_object_or_404(Reservation, pk=pk)

    if request.method != 'POST':
        return redirect('reservations:gate_verify')

    action = request.POST.get('action')
    handlers = {'check_in': services.check_in, 'check_out': services.check_out}
    handler = handlers.get(action)

    if handler is None:
        messages.error(request, 'Unknown gate action.')
    else:
        try:
            handler(reservation, actor=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            verb = 'checked in' if action == 'check_in' else 'checked out'
            messages.success(request, f'{reservation.reference} {verb}.')

    # Back to the lookup with the same reference pre-filled, so the staff
    # member sees the booking's new state. Never redirect to the Referer
    # header — it's attacker-controllable.
    return redirect(f"{reverse('reservations:gate_verify')}?reference={reservation.reference}")
