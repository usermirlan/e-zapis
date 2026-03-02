import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Service, Specialist, TimeSlot, Appointment



def home_view(request):
    
    services = Service.objects.filter(is_active=True)
    specialists_count = Specialist.objects.filter(is_active=True).count()
    appointments_count = Appointment.objects.count()

    return render(request, 'queue_app/home.html', {
        'services': services,
        'specialists_count': specialists_count,
        'appointments_count': appointments_count,
    })


# ─── Услуги ───────────────────────────────────────────────────────────────────

def services_view(request):
    
    services = Service.objects.filter(is_active=True).prefetch_related('specialists')
    return render(request, 'queue_app/services.html', {'services': services})



def specialists_view(request, service_id=None):
  
    services = Service.objects.filter(is_active=True)

    if service_id:
        service = get_object_or_404(Service, pk=service_id, is_active=True)
        specialists = Specialist.objects.filter(service=service, is_active=True)
    else:
        service = None
        specialists = Specialist.objects.filter(is_active=True).select_related('service')

    return render(request, 'queue_app/specialists.html', {
        'specialists': specialists,
        'services': services,
        'selected_service': service,
    })


def specialist_detail_view(request, specialist_id):

    specialist = get_object_or_404(Specialist, pk=specialist_id, is_active=True)

    today = timezone.now().date()
    available_slots = TimeSlot.objects.filter(
        specialist=specialist,
        is_available=True,
        date__gte=today
    ).order_by('date', 'time')

    slots_by_date = {}
    for slot in available_slots:
        date_key = slot.date
        if date_key not in slots_by_date:
            slots_by_date[date_key] = []
        slots_by_date[date_key].append(slot)

    return render(request, 'queue_app/specialist_detail.html', {
        'specialist': specialist,
        'slots_by_date': slots_by_date,
        'today': today,
    })



@login_required
def booking_view(request, slot_id):

    slot = get_object_or_404(TimeSlot, pk=slot_id, is_available=True)
    specialist = slot.specialist

    if slot.date < timezone.now().date():
        messages.error(request, 'Этот слот уже недоступен.')
        return redirect('specialist_detail', specialist_id=specialist.pk)

    if request.method == 'POST':
        complaint = request.POST.get('complaint', '')

        slot.refresh_from_db()
        if not slot.is_available:
            messages.error(request, 'К сожалению, этот слот уже занят. Выберите другое время.')
            return redirect('specialist_detail', specialist_id=specialist.pk)

        appointment = Appointment.objects.create(
            patient=request.user,
            service=specialist.service,
            specialist=specialist,
            time_slot=slot,
            complaint=complaint,
        )

        messages.success(request, f'Вы успешно встали в очередь! Номер талона: #{appointment.queue_number}. Ожидайте подтверждения.')
        return redirect('appointment_success', appointment_id=appointment.pk)

    return render(request, 'queue_app/booking.html', {
        'slot': slot,
        'specialist': specialist,
    })


@login_required
def appointment_success_view(request, appointment_id):
    """
    Страница подтверждения — отображает номер очереди после успешной записи.
    """
    appointment = get_object_or_404(Appointment, pk=appointment_id, patient=request.user)
    return render(request, 'queue_app/appointment_success.html', {
        'appointment': appointment,
    })


@login_required
def my_appointments_view(request):
   
    appointments = Appointment.objects.filter(
        patient=request.user
    ).select_related('specialist', 'service', 'time_slot').order_by('-created_at')

    return render(request, 'queue_app/my_appointments.html', {
        'appointments': appointments,
    })


@login_required
@require_POST
def cancel_appointment_view(request, appointment_id):
    
    appointment = get_object_or_404(Appointment, pk=appointment_id, patient=request.user)

    # Можно отменить только ожидающие записи
    if appointment.status in ('pending', 'confirmed'):
        appointment.status = 'cancelled'
        appointment.save()

        # Освобождаем временной слот
        appointment.time_slot.is_available = True
        appointment.time_slot.save()

        messages.success(request, 'Запись успешно отменена.')
    else:
        messages.error(request, 'Невозможно отменить эту запись.')

    return redirect('my_appointments')



def api_services(request):
   
    services = Service.objects.filter(is_active=True).values(
        'id', 'name', 'description', 'icon', 'duration_minutes'
    )
    return JsonResponse({'services': list(services)})


def api_specialists(request):
    service_id = request.GET.get('service_id')
    qs = Specialist.objects.filter(is_active=True).select_related('service')

    if service_id:
        qs = qs.filter(service_id=service_id)

    data = []
    for s in qs:
        data.append({
            'id': s.id,
            'full_name': s.get_full_name(),
            'service': s.service.name,
            'experience_years': s.experience_years,
            'cabinet': s.cabinet,
            'bio': s.bio,
            'photo_url': s.photo.url if s.photo else None,
        })

    return JsonResponse({'specialists': data})


def api_time_slots(request, specialist_id):

    specialist = get_object_or_404(Specialist, pk=specialist_id, is_active=True)
    today = timezone.now().date()

    slots = TimeSlot.objects.filter(
        specialist=specialist,
        is_available=True,
        date__gte=today
    ).order_by('date', 'time')

    data = [
        {
            'id': slot.id,
            'date': str(slot.date),
            'time': str(slot.time)[:5],  # Формат HH:MM
        }
        for slot in slots
    ]

    return JsonResponse({'slots': data, 'specialist_id': specialist_id})
