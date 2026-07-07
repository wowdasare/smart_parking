from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import VehicleForm
from .models import Vehicle


class OwnerVehicleQuerysetMixin(LoginRequiredMixin):
    """Scopes every view in this module to the current user's own vehicles."""

    model = Vehicle

    def get_queryset(self):
        return Vehicle.objects.filter(owner=self.request.user)


class VehicleListView(OwnerVehicleQuerysetMixin, ListView):
    template_name = 'vehicles/vehicle_list.html'
    context_object_name = 'vehicles'


class VehicleCreateView(LoginRequiredMixin, CreateView):
    model = Vehicle
    form_class = VehicleForm
    template_name = 'vehicles/vehicle_form.html'
    success_url = reverse_lazy('vehicles:list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, 'Vehicle added successfully.')
        return super().form_valid(form)


class VehicleUpdateView(OwnerVehicleQuerysetMixin, UpdateView):
    form_class = VehicleForm
    template_name = 'vehicles/vehicle_form.html'
    success_url = reverse_lazy('vehicles:list')

    def form_valid(self, form):
        messages.success(self.request, 'Vehicle updated successfully.')
        return super().form_valid(form)


class VehicleDeleteView(OwnerVehicleQuerysetMixin, DeleteView):
    template_name = 'vehicles/vehicle_confirm_delete.html'
    success_url = reverse_lazy('vehicles:list')

    def form_valid(self, form):
        messages.success(self.request, 'Vehicle removed.')
        return super().form_valid(form)
