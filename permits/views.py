from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User

from . import services
from .forms import PermitApplicationForm, PermitReviewForm, PlateCheckForm
from .models import Permit


def _is_office_staff(user):
    """Who may review applications: the parking office (admins)."""
    return user.is_superuser or user.role == User.Role.ADMIN


def _is_gate_staff(user):
    """Who may check plates at the gate: security and admins."""
    return user.is_superuser or user.role in (User.Role.SECURITY, User.Role.ADMIN)


def _permit_queryset():
    return Permit.objects.select_related('holder', 'vehicle', 'zone', 'reviewed_by')


def _own_permits(user):
    """Only the holder's own — the scope for acting on an application."""
    return _permit_queryset().filter(holder=user)


def _listable_permits(user):
    """The list screen: the office manages the whole queue, everyone else
    sees their own applications.
    """
    if _is_office_staff(user):
        return _permit_queryset()
    return _own_permits(user)


def _viewable_permits(user):
    """Detail is wider than list: gate staff must be able to open the permit
    they just matched by plate. Reviewing it stays office-only (enforced in
    permit_review), and withdrawing stays holder-only (_own_permits).
    """
    if _is_gate_staff(user):
        return _permit_queryset()
    return _own_permits(user)


@login_required
def permit_list(request):
    services.expire_lapsed()

    permits = _listable_permits(request.user)
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    if query:
        permits = permits.filter(
            Q(permit_number__icontains=query)
            | Q(vehicle__registration_number__icontains=query)
            | Q(holder__username__icontains=query)
            | Q(holder__first_name__icontains=query)
            | Q(holder__last_name__icontains=query)
        )
    if status:
        permits = permits.filter(status=status)

    permits = list(permits)
    context = {
        'permits': permits,
        'query': query,
        'status': status,
        'status_choices': Permit.Status.choices,
        'is_office_staff': _is_office_staff(request.user),
        'can_apply': request.user.vehicles.exists(),
        'pending_count': sum(1 for p in permits if p.status == Permit.Status.PENDING),
        'active_count': sum(1 for p in permits if p.is_current),
    }
    return render(request, 'permits/permit_list.html', context)


@login_required
def permit_apply(request):
    if request.method == 'POST':
        form = PermitApplicationForm(request.POST, request.FILES, holder=request.user)
        if form.is_valid():
            permit = services.submit_application(form.instance, actor=request.user)
            messages.success(
                request,
                'Application submitted. The parking office will review it shortly.',
            )
            return redirect('permits:detail', pk=permit.pk)
    else:
        start, end = PermitApplicationForm.suggested_dates()
        form = PermitApplicationForm(
            holder=request.user,
            initial={'valid_from': start, 'valid_until': end},
        )

    return render(request, 'permits/permit_form.html', {
        'form': form,
        'has_vehicles': request.user.vehicles.exists(),
        'fees': Permit.DEFAULT_FEES.items(),
    })


@login_required
def permit_detail(request, pk):
    permit = get_object_or_404(_viewable_permits(request.user), pk=pk)
    return render(request, 'permits/permit_detail.html', {
        'permit': permit,
        'review_form': PermitReviewForm(),
        'is_office_staff': _is_office_staff(request.user),
    })


@login_required
def permit_document(request, pk):
    """Serves a permit's supporting document through the permission check.

    Supporting documents are student IDs and appointment letters — linking
    straight to MEDIA_URL would make them readable by anyone holding the URL,
    and wouldn't serve at all once DEBUG is off. Going through a view means
    the same _viewable_permits scoping that guards the detail page guards the
    file, in dev and in production alike.
    """
    permit = get_object_or_404(_viewable_permits(request.user), pk=pk)

    if not permit.document:
        raise Http404('This permit has no attached document.')

    return FileResponse(
        permit.document.open('rb'),
        as_attachment=True,
        filename=permit.document.name.rsplit('/', 1)[-1],
    )


@login_required
def permit_review(request, pk):
    """Approve, reject, revoke, or mark paid. Office staff only, POST only."""
    if not _is_office_staff(request.user):
        raise PermissionDenied('Only the parking office can review permit applications.')

    permit = get_object_or_404(Permit, pk=pk)

    if request.method != 'POST':
        return redirect('permits:detail', pk=permit.pk)

    form = PermitReviewForm(request.POST)
    note = form.cleaned_data['note'] if form.is_valid() else ''
    action = request.POST.get('action')

    try:
        if action == 'approve':
            services.approve(permit, reviewer=request.user, note=note)
            messages.success(request, f'Permit approved as {permit.permit_number}.')
        elif action == 'reject':
            services.reject(permit, reviewer=request.user, note=note)
            messages.success(request, 'Application rejected and the applicant notified.')
        elif action == 'revoke':
            services.revoke(permit, actor=request.user, note=note)
            messages.success(request, 'Permit revoked and the holder notified.')
        elif action == 'mark_paid':
            services.mark_paid(permit, actor=request.user)
            messages.success(request, 'Fee recorded as paid.')
        else:
            messages.error(request, 'Unknown permit action.')
    except ValueError as exc:
        messages.error(request, str(exc))

    return redirect('permits:detail', pk=permit.pk)


@login_required
def permit_withdraw(request, pk):
    """The applicant pulls their own pending application."""
    permit = get_object_or_404(_own_permits(request.user), pk=pk)

    if request.method != 'POST':
        return render(request, 'permits/permit_confirm_withdraw.html', {'permit': permit})

    try:
        services.withdraw(permit, actor=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'Application withdrawn.')
    return redirect('permits:list')


@login_required
def plate_check(request):
    """Gate-side answer to 'is this plate allowed on campus?'"""
    if not _is_gate_staff(request.user):
        raise PermissionDenied('Plate checks are limited to security staff.')

    services.expire_lapsed(actor=request.user)

    permit = None
    searched = None
    form = PlateCheckForm(request.GET or None)
    if form.is_valid():
        searched = form.cleaned_data['plate']
        permit = services.permit_for_plate(searched)

    context = {
        'form': form,
        'permit': permit,
        'searched': searched,
        # Shown alongside the result so staff can see what a plate with no
        # current cover does have on file — expired, revoked, or pending.
        'other_permits': (
            Permit.objects
            .for_plate(searched)
            .select_related('holder', 'vehicle', 'zone')
            .exclude(pk=permit.pk if permit else None)
            if searched else Permit.objects.none()
        ),
        'expiring_soon': [
            p for p in Permit.objects.active().select_related('holder', 'vehicle')
            if p.expires_soon
        ],
    }
    return render(request, 'permits/plate_check.html', context)
