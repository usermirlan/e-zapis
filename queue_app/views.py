import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q
from .models import Service, Specialist, TimeSlot, Appointment
from .forms import BookingForm


# ─── Вспомогательная функция ──────────────────────────────────────────────────

def is_staff_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


# ─── Главная ──────────────────────────────────────────────────────────────────

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


# ─── Специалисты ──────────────────────────────────────────────────────────────

def specialists_view(request, service_id=None):
    services = Service.objects.filter(is_active=True)
    search_query = request.GET.get('q', '').strip()

    if service_id:
        service = get_object_or_404(Service, pk=service_id, is_active=True)
        specialists = Specialist.objects.filter(service=service, is_active=True)
    else:
        service = None
        specialists = Specialist.objects.filter(is_active=True).select_related('service')

    # ── Поиск по имени / фамилии ──
    if search_query:
        specialists = specialists.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(middle_name__icontains=search_query) |
            Q(service__name__icontains=search_query)
        )

    return render(request, 'queue_app/specialists.html', {
        'specialists': specialists,
        'services': services,
        'selected_service': service,
        'search_query': search_query,
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


# ─── Запись на приём ──────────────────────────────────────────────────────────

@login_required
def booking_view(request, slot_id):
    slot = get_object_or_404(TimeSlot, pk=slot_id, is_available=True)
    specialist = slot.specialist

    if slot.date < timezone.now().date():
        messages.error(request, 'Этот слот уже недоступен.')
        return redirect('specialist_detail', specialist_id=specialist.pk)

    # ── Защита от двойной записи ──
    already_booked = Appointment.objects.filter(
        patient=request.user,
        specialist=specialist,
        time_slot__date=slot.date,
        status__in=('pending', 'confirmed')
    ).exists()

    if already_booked:
        messages.warning(
            request,
            f'Вы уже записаны к {specialist.get_full_name()} на {slot.date.strftime("%d.%m.%Y")}. '
            f'Чтобы изменить запись, сначала отмените предыдущую.'
        )
        return redirect('specialist_detail', specialist_id=specialist.pk)

    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            slot.refresh_from_db()
            if not slot.is_available:
                messages.error(request, 'К сожалению, этот слот уже занят. Выберите другое время.')
                return redirect('specialist_detail', specialist_id=specialist.pk)

            appointment = Appointment.objects.create(
                patient=request.user,
                service=specialist.service,
                specialist=specialist,
                time_slot=slot,
                complaint=form.cleaned_data['complaint'],
            )

            # ── Email-уведомление ──
            _send_appointment_email(appointment, action='created')

            messages.success(
                request,
                f'Вы успешно встали в очередь! Номер талона: #{appointment.queue_number}. '
                f'Ожидайте подтверждения.'
            )
            return redirect('appointment_success', appointment_id=appointment.pk)
    else:
        form = BookingForm()

    return render(request, 'queue_app/booking.html', {
        'slot': slot,
        'specialist': specialist,
        'form': form,
    })


@login_required
def appointment_success_view(request, appointment_id):
    appointment = get_object_or_404(Appointment, pk=appointment_id, patient=request.user)
    return render(request, 'queue_app/appointment_success.html', {
        'appointment': appointment,
    })


# ─── Личный кабинет ───────────────────────────────────────────────────────────

@login_required
def my_appointments_view(request):
    appointments_qs = Appointment.objects.filter(
        patient=request.user
    ).select_related('specialist', 'service', 'time_slot').order_by('-created_at')

    paginator = Paginator(appointments_qs, 10)
    page = request.GET.get('page', 1)
    appointments = paginator.get_page(page)

    return render(request, 'queue_app/my_appointments.html', {
        'appointments': appointments,
    })


@login_required
@require_POST
def cancel_appointment_view(request, appointment_id):
    appointment = get_object_or_404(Appointment, pk=appointment_id, patient=request.user)

    if appointment.status in ('pending', 'confirmed'):
        appointment.status = 'cancelled'
        appointment.save()

        # Освобождаем временной слот
        appointment.time_slot.is_available = True
        appointment.time_slot.save()

        # ── Email-уведомление об отмене ──
        _send_appointment_email(appointment, action='cancelled')

        messages.success(request, 'Запись успешно отменена.')
    else:
        messages.error(request, 'Невозможно отменить эту запись.')

    return redirect('my_appointments')


# ─── Панель сотрудника ────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def staff_panel_view(request):
    """Панель для сотрудников: просмотр и управление записями."""
    today = timezone.now().date()

    # Фильтры
    selected_date = request.GET.get('date', str(today))
    specialist_id = request.GET.get('specialist', '')
    status_filter = request.GET.get('status', '')

    appointments_qs = Appointment.objects.select_related(
        'patient', 'specialist', 'service', 'time_slot'
    )

    # Фильтр по дате
    try:
        from datetime import date as date_type
        import datetime
        filter_date = datetime.date.fromisoformat(selected_date)
        appointments_qs = appointments_qs.filter(time_slot__date=filter_date)
    except (ValueError, TypeError):
        filter_date = today
        appointments_qs = appointments_qs.filter(time_slot__date=today)

    if specialist_id:
        appointments_qs = appointments_qs.filter(specialist_id=specialist_id)

    if status_filter:
        appointments_qs = appointments_qs.filter(status=status_filter)

    appointments_qs = appointments_qs.order_by('time_slot__time', 'queue_number')

    paginator = Paginator(appointments_qs, 20)
    page = request.GET.get('page', 1)
    appointments = paginator.get_page(page)

    specialists = Specialist.objects.filter(is_active=True).select_related('service')

    return render(request, 'queue_app/staff_panel.html', {
        'appointments': appointments,
        'specialists': specialists,
        'selected_date': str(filter_date),
        'selected_specialist': specialist_id,
        'selected_status': status_filter,
        'status_choices': Appointment.STATUS_CHOICES,
        'today': str(today),
    })


@login_required
@user_passes_test(is_staff_user, login_url='home')
@require_POST
def update_appointment_status_view(request, appointment_id):
    """AJAX/POST: смена статуса записи сотрудником."""
    appointment = get_object_or_404(Appointment, pk=appointment_id)
    new_status = request.POST.get('status')
    valid_statuses = [s[0] for s in Appointment.STATUS_CHOICES]

    if new_status not in valid_statuses:
        messages.error(request, 'Неверный статус.')
        return redirect('staff_panel')

    old_status = appointment.status
    appointment.status = new_status
    appointment.save()

    # Если завершена или отменена — освобождаем слот при отмене
    if new_status == 'cancelled' and old_status != 'cancelled':
        appointment.time_slot.is_available = True
        appointment.time_slot.save()
        _send_appointment_email(appointment, action='cancelled')

    status_labels = {
        'pending': 'Ожидает',
        'confirmed': 'Подтверждена',
        'completed': 'Завершена',
        'cancelled': 'Отменена',
    }
    messages.success(
        request,
        f'Статус записи #{appointment.queue_number} изменён на «{status_labels.get(new_status, new_status)}».'
    )
    return redirect(request.POST.get('next', 'staff_panel'))


# ─── Email-уведомления ────────────────────────────────────────────────────────

def _send_appointment_email(appointment, action='created'):
    """Отправляет email пациенту при создании или отмене записи."""
    patient = appointment.patient
    if not patient.email:
        return

    specialist_name = appointment.specialist.get_full_name()
    slot_date = appointment.time_slot.date.strftime('%d.%m.%Y')
    slot_time = appointment.time_slot.time.strftime('%H:%M')

    if action == 'created':
        subject = f'МедЗапись — Запись №{appointment.queue_number} подтверждена'
        body = (
            f'Здравствуйте, {patient.get_full_name()}!\n\n'
            f'Вы успешно записаны на приём:\n'
            f'  Врач:     {specialist_name}\n'
            f'  Услуга:   {appointment.service.name}\n'
            f'  Дата:     {slot_date}\n'
            f'  Время:    {slot_time}\n'
            f'  Кабинет:  {appointment.specialist.cabinet or "уточняйте на месте"}\n'
            f'  Талон №:  {appointment.queue_number}\n\n'
            f'Пожалуйста, приходите за 10 минут до приёма.\n\n'
            f'С уважением, МедЗапись'
        )
    elif action == 'cancelled':
        subject = f'МедЗапись — Запись №{appointment.queue_number} отменена'
        body = (
            f'Здравствуйте, {patient.get_full_name()}!\n\n'
            f'Ваша запись была отменена:\n'
            f'  Врач:   {specialist_name}\n'
            f'  Дата:   {slot_date}\n'
            f'  Время:  {slot_time}\n\n'
            f'Вы можете записаться снова на нашем сайте.\n\n'
            f'С уважением, МедЗапись'
        )
    else:
        return

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@medzapis.kz'),
            recipient_list=[patient.email],
            fail_silently=True,
        )
    except Exception:
        pass  # Не прерываем работу, если email не отправился


# ─── API-эндпоинты (JSON) ─────────────────────────────────────────────────────

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
            'time': str(slot.time)[:5],
        }
        for slot in slots
    ]

    return JsonResponse({'slots': data, 'specialist_id': specialist_id})
