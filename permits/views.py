from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def permit_list(request):
    return render(request, 'permits/permit_list.html')
