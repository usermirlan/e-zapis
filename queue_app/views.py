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
from django.db.models import Q, Avg, Count
from django.views.generic import TemplateView, View, CreateView, UpdateView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator

from .models import Service, Specialist, TimeSlot, Appointment, Review, Notification
from .forms import BookingForm, ServiceForm, SpecialistForm, ReviewForm, MedicalRecordForm, SlotGenerationForm
from accounts.forms import DoctorRegisterForm

# ─── Вспомогательная функция ──────────────────────────────────────────────────

def is_staff_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


# ─── Главная ──────────────────────────────────────────────────────────────────

def home_view(request):
    if request.user.is_authenticated and request.user.is_doctor:
        return redirect('doctor_dashboard')
        
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
    if request.user.is_authenticated and request.user.is_doctor:
        return redirect('doctor_dashboard')
        
    services = Service.objects.filter(is_active=True).prefetch_related('specialists')
    return render(request, 'queue_app/services.html', {'services': services})


# ─── Специалисты ──────────────────────────────────────────────────────────────

def specialists_view(request, service_id=None):
    if request.user.is_authenticated and request.user.is_doctor:
        return redirect('doctor_dashboard')
        
    services = Service.objects.filter(is_active=True)
    search_query = request.GET.get('q', '').strip()
    order_by = request.GET.get('order', 'name')

    if service_id:
        service = get_object_or_404(Service, pk=service_id, is_active=True)
        specialists = Specialist.objects.filter(service=service, is_active=True)
    else:
        service = None
        specialists = Specialist.objects.filter(is_active=True).select_related('service')

    # ── Аннотация средним рейтингом для сортировки ──
    specialists = specialists.annotate(avg_rating=Avg('reviews__rating'))

    # ── Поиск по имени / фамилии ──
    if search_query:
        specialists = specialists.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(middle_name__icontains=search_query) |
            Q(service__name__icontains=search_query)
        )

    # ── Сортировка ──
    if order_by == 'rating':
        specialists = specialists.order_by('-avg_rating', 'last_name')
    elif order_by == 'experience':
        specialists = specialists.order_by('-experience_years', 'last_name')
    else: # по умолчанию (name)
        specialists = specialists.order_by('last_name', 'first_name')

    return render(request, 'queue_app/specialists.html', {
        'specialists': specialists,
        'services': services,
        'selected_service': service,
        'search_query': search_query,
        'order_by': order_by,
    })


def specialist_detail_view(request, specialist_id):
    if request.user.is_authenticated and request.user.is_doctor:
        return redirect('doctor_dashboard')
        
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

            # ── Уведомление врачу ──
            Notification.objects.create(
                user=specialist.user,
                appointment=appointment,
                notification_type='new_appointment',
                message=f'Новая запись: {request.user.get_full_name()} на {slot.date.strftime("%d.%m.%Y")} в {slot.time.strftime("%H:%M")}',
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
    if request.user.is_doctor:
        return redirect('doctor_dashboard')
        
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
def patient_notifications_view(request):
    """Страница уведомлений для пациента."""
    notifications = Notification.objects.filter(
        user=request.user
    ).select_related('appointment').order_by('-created_at')[:50]

    return render(request, 'queue_app/notifications.html', {
        'notifications': notifications,
    })


@login_required
@require_POST
def patient_mark_all_read_view(request):
    """Отметить все уведомления пациента как прочитанные."""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('patient_notifications')


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


@login_required
def add_review_view(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    
    # Можно оставлять отзыв только для завершенных приемов
    if appointment.status != 'completed':
        messages.error(request, 'Вы можете оставить отзыв только после завершения приема.')
        return redirect('my_appointments')

    # Проверка, не оставлен ли отзыв ранее
    if hasattr(appointment, 'review'):
        messages.warning(request, 'Вы уже оставили отзыв для этого приема.')
        return redirect('my_appointments')

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.patient = request.user
            review.specialist = appointment.specialist
            review.appointment = appointment
            review.save()
            messages.success(request, 'Спасибо за ваш отзыв!')
            return redirect('my_appointments')
    else:
        form = ReviewForm()

    return render(request, 'queue_app/add_review.html', {
        'form': form,
        'appointment': appointment
    })


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
def staff_add_doctor_view(request):
    """Страница для добавления новых врачей (Доступна только Администраторам)."""
    if request.method == 'POST':
        form = DoctorRegisterForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            # Добавляем специалиста в группу и тд, но форма сама всё делает.
            messages.success(request, f'Врач {user.get_full_name()} успешно добавлен! Расписание сгенерировано.')
            return redirect('staff_panel')
        else:
            messages.error(request, 'Пожалуйста, проверьте правильность заполнения формы.')
    else:
        form = DoctorRegisterForm()

    return render(request, 'queue_app/staff_add_doctor.html', {'form': form})


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




# ─── Утилита: проверка "является ли врачом" ───────────────────────────────────

def is_doctor(user):
    return user.is_authenticated and user.is_doctor and hasattr(user, 'specialist_profile')


def doctor_required(view_func):
    """Декоратор: доступ только для врачей."""
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_doctor(request.user):
            messages.error(request, 'У вас нет доступа к кабинету врача.')
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── Кабинет врача: Главная панель ────────────────────────────────────────────

@doctor_required
def doctor_dashboard_view(request):
    specialist = request.user.specialist_profile
    today = timezone.now().date()
    week_ago = today - timezone.timedelta(days=7)
    month_ago = today - timezone.timedelta(days=30)

    all_appointments = Appointment.objects.filter(specialist=specialist)

    # Статистика
    today_count = all_appointments.filter(time_slot__date=today).count()
    week_count = all_appointments.filter(time_slot__date__gte=week_ago).count()
    month_count = all_appointments.filter(time_slot__date__gte=month_ago).count()
    total_count = all_appointments.count()

    # Записи на сегодня
    today_appointments = all_appointments.filter(
        time_slot__date=today
    ).select_related('patient', 'service', 'time_slot').order_by('time_slot__time')

    # Статистика по статусам (для графика)
    status_stats = list(all_appointments.values('status').annotate(count=Count('status')))
    
    # Подготовка данных для Chart.js
    # Формат: {'pending': 5, 'confirmed': 10, ...}
    status_data = {item['status']: item['count'] for item in status_stats}
    
    # Динамика посещений (последние 7 дней)
    days_list = []
    counts_list = []
    for i in range(6, -1, -1):
        d = today - timezone.timedelta(days=i)
        days_list.append(d.strftime('%d.%m'))
        counts_list.append(all_appointments.filter(time_slot__date=d).count())

    # Непрочитанные уведомления
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()

    return render(request, 'doctor/doctor_dashboard.html', {
        'specialist': specialist,
        'today_count': today_count,
        'week_count': week_count,
        'month_count': month_count,
        'total_count': total_count,
        'today_appointments': today_appointments,
        'unread_count': unread_count,
        'status_data': status_data,
        'days_list': days_list,
        'counts_list': counts_list,
    })


# ─── Кабинет врача: Все записи ───────────────────────────────────────────────

@doctor_required
def doctor_appointments_view(request):
    specialist = request.user.specialist_profile
    today = timezone.now().date()
    filter_type = request.GET.get('filter', 'all')

    appointments = Appointment.objects.filter(
        specialist=specialist
    ).select_related('patient', 'service', 'time_slot')

    if filter_type == 'today':
        appointments = appointments.filter(time_slot__date=today)
    elif filter_type == 'week':
        week_ago = today - timezone.timedelta(days=7)
        appointments = appointments.filter(time_slot__date__gte=week_ago)
    elif filter_type == 'month':
        month_ago = today - timezone.timedelta(days=30)
        appointments = appointments.filter(time_slot__date__gte=month_ago)
    elif filter_type == 'upcoming':
        appointments = appointments.filter(
            time_slot__date__gte=today,
            status__in=['pending', 'confirmed']
        )

    appointments = appointments.order_by('-time_slot__date', '-time_slot__time')

    return render(request, 'doctor/doctor_appointments.html', {
        'appointments': appointments,
        'filter_type': filter_type,
    })


# ─── Кабинет врача: Обновить статус записи ───────────────────────────────────

@doctor_required
@require_POST
def doctor_update_status_view(request, appointment_id):
    specialist = request.user.specialist_profile
    appointment = get_object_or_404(Appointment, pk=appointment_id, specialist=specialist)
    new_status = request.POST.get('status')

    if new_status in dict(Appointment.STATUS_CHOICES):
        old_status = appointment.get_status_display()
        appointment.status = new_status
        appointment.save()

        # Если отменена — вернуть слот
        if new_status == 'cancelled':
            appointment.time_slot.is_available = True
            appointment.time_slot.save()

        messages.success(
            request,
            f'Статус записи #{appointment.queue_number} изменён: {old_status} → {appointment.get_status_display()}'
        )

        # ── Уведомление пациенту ──
        status_msg = f'Статус вашего приема у врача {specialist.get_full_name()} изменен на "{appointment.get_status_display()}".'
        Notification.objects.create(
            user=appointment.patient,
            appointment=appointment,
            notification_type='status_update',
            message=status_msg
        )

        # ── Real-Time WebSocket broadcast ──
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        group_name = f'queue_{specialist.id}'
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'queue_update',
                'appointment_id': appointment.id,
                'status': appointment.status,
                'status_display': appointment.get_status_display(),
                'queue_number': appointment.queue_number,
            }
        )
    else:
        messages.error(request, 'Неверный статус.')

    return redirect('doctor_appointments')


@doctor_required
def doctor_add_medical_record_view(request, appointment_id):
    """Страница добавления мед. записи (диагноз, рекомендации)."""
    specialist = request.user.specialist_profile
    appointment = get_object_or_404(Appointment, pk=appointment_id, specialist=specialist)

    # Запись можно создать только если прием завершен или переводится в завершенные
    if appointment.status == 'cancelled':
        messages.error(request, "Нельзя добавить мед. запись к отмененному приему.")
        return redirect('doctor_appointments')

    # Проверяем, существует ли уже запись
    if hasattr(appointment, 'medical_record'):
        messages.info(request, "У этой записи уже есть медицинский протокол.")
        return redirect('doctor_appointments')

    if request.method == 'POST':
        form = MedicalRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.appointment = appointment
            record.save()
            
            # Автоматически помечаем прием как завершенный
            if appointment.status != 'completed':
                appointment.status = 'completed'
                appointment.save()
                
            messages.success(request, f"Медицинская запись для {appointment.patient.get_full_name()} успешно сохранена.")
            return redirect('doctor_appointments')
    else:
        form = MedicalRecordForm()

    return render(request, 'doctor/add_medical_record.html', {
        'form': form,
        'appointment': appointment
    })


# ─── Кабинет врача: Список пациентов ─────────────────────────────────────────

@doctor_required
def doctor_patients_view(request):
    specialist = request.user.specialist_profile
    search_query = request.GET.get('q', '').strip()

    # Все уникальные пациенты этого врача
    patient_ids = Appointment.objects.filter(
        specialist=specialist
    ).values_list('patient_id', flat=True).distinct()

    from accounts.models import CustomUser
    patients = CustomUser.objects.filter(id__in=patient_ids)

    if search_query:
        patients = patients.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    # Для каждого пациента — кол-во визитов и последний визит
    patient_data = []
    for patient in patients:
        appts = Appointment.objects.filter(
            specialist=specialist, patient=patient
        ).order_by('-time_slot__date')
        patient_data.append({
            'patient': patient,
            'visit_count': appts.count(),
            'last_visit': appts.first(),
        })

    return render(request, 'doctor/doctor_patients.html', {
        'patient_data': patient_data,
        'search_query': search_query,
    })


# ─── Кабинет врача: Уведомления ──────────────────────────────────────────────

@doctor_required
def doctor_notifications_view(request):
    specialist = request.user.specialist_profile
    notifications = Notification.objects.filter(
        user=request.user
    ).select_related('appointment').order_by('-created_at')[:50]

    return render(request, 'doctor/doctor_notifications.html', {
        'notifications': notifications,
    })


@doctor_required
@require_POST
def doctor_mark_read_view(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return redirect('doctor_notifications')


@doctor_required
@require_POST
def doctor_mark_all_read_view(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, 'Все уведомления отмечены как прочитанные.')
    return redirect('doctor_notifications')


# ─── Кабинет врача: Профиль ──────────────────────────────────────────────────

@doctor_required
def doctor_profile_view(request):
    specialist = request.user.specialist_profile
    user = request.user

    if request.method == 'POST':
        # Данные пользователя
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.phone = request.POST.get('phone', user.phone)
        user.save()

        # Данные специалиста
        specialist.first_name = user.first_name
        specialist.last_name = user.last_name
        specialist.middle_name = request.POST.get('middle_name', specialist.middle_name)
        
        specialist.bio = request.POST.get('bio', specialist.bio)
        specialist.cabinet = request.POST.get('cabinet', specialist.cabinet)
        specialist.work_start = request.POST.get('work_start', '09:00')
        specialist.work_end = request.POST.get('work_end', '18:00')
        experience = request.POST.get('experience_years', 0)
        specialist.experience_years = int(experience) if experience else 0

        if 'photo' in request.FILES:
            specialist.photo = request.FILES['photo']

        specialist.save()
        messages.success(request, 'Профиль успешно обновлён!')
        return redirect('doctor_profile')

    return render(request, 'doctor/doctor_profile.html', {
        'specialist': specialist,
        'user': user,
    })


@doctor_required
def doctor_generate_slots_view(request):
    """Страница автоматической генерации слотов врачом."""
    specialist = request.user.specialist_profile
    
    if request.method == 'POST':
        form = SlotGenerationForm(request.POST)
        if form.is_valid():
            days = form.cleaned_data['days']
            duration = specialist.service.duration_minutes
            work_start = specialist.work_start
            work_end = specialist.work_end
            
            today = timezone.now().date()
            created_count = 0
            
            from datetime import datetime, timedelta
            
            for day_offset in range(days):
                current_date = today + timedelta(days=day_offset)
                
                # Пропускаем воскресенье
                if current_date.weekday() == 6:
                    continue
                    
                current_time_dt = datetime.combine(current_date, work_start)
                end_time_dt = datetime.combine(current_date, work_end)
                
                while current_time_dt < end_time_dt:
                    slot_time = current_time_dt.time()
                    
                    _, created = TimeSlot.objects.get_or_create(
                        specialist=specialist,
                        date=current_date,
                        time=slot_time,
                        defaults={'is_available': True}
                    )
                    if created:
                        created_count += 1
                        
                    current_time_dt += timedelta(minutes=duration)
            
            messages.success(request, f'Успешно создано {created_count} новых временных слотов на ближайшие {days} дн.')
            return redirect('doctor_appointments')
    else:
        form = SlotGenerationForm()
        
    return render(request, 'doctor/generate_slots.html', {
        'form': form,
        'specialist': specialist
    })
