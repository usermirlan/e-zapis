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
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView, View, CreateView, UpdateView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator

from .models import Service, Specialist, TimeSlot, Appointment, Review, Notification, SpecialistAbsence
from .forms import BookingForm, ServiceForm, SpecialistForm, ReviewForm, MedicalRecordForm, SlotGenerationForm, ManualSlotForm
from accounts.forms import DoctorRegisterForm

# ─── Вспомогательная функция ──────────────────────────────────────────────────

def is_staff_user(user):
    return user.is_authenticated and user.is_active and (user.is_staff or user.is_superuser)


# ─── Главная ──────────────────────────────────────────────────────────────────

def home_view(request):
    if request.user.is_authenticated and request.user.is_doctor:
        return redirect('doctor_dashboard')
        
    services = Service.objects.filter(is_active=True)
    specialists_count = Specialist.objects.filter(is_active=True).count()
    appointments_count = Appointment.objects.count()

    # Динамический расчет времени ожидания
    today = timezone.now().date()
    active_appointments = Appointment.objects.filter(
        time_slot__date=today,
        status__in=['pending', 'confirmed']
    ).count()

    if specialists_count > 0:
        # Примерный расчет: (количество активных записей / кол-во врачей) * 10 минут
        wait_time = (active_appointments // specialists_count) * 10
    else:
        wait_time = 0

    return render(request, 'queue_app/home.html', {
        'services': services,
        'specialists_count': specialists_count,
        'appointments_count': appointments_count,
        'wait_time': wait_time,
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
            if specialist.user:
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
    """Перенаправление со старой панели на современную админку."""
    return redirect('admin_dashboard')




@login_required
@user_passes_test(is_staff_user, login_url='home')
def staff_add_doctor_view(request):
    """Добавление нового врача через форму в новой админке."""
    if request.method == 'POST':
        form = DoctorRegisterForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Врач {user.get_full_name()} успешно добавлен в систему! Расписание на 30 дней создано автоматически.')
            return redirect('admin_specialists')
        else:
            messages.error(request, 'Ошибка при добавлении врача. Пожалуйста, проверьте поля формы.')
    else:
        form = DoctorRegisterForm()

    return render(request, 'admin_panel/specialist_add.html', {'form': form})



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
        return redirect('admin_dashboard')


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
    return redirect(request.POST.get('next', 'admin_dashboard'))



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
    return user.is_authenticated and user.is_active and user.is_doctor and hasattr(user, 'specialist_profile')


def doctor_required(view_func):
    """Декоратор: доступ только для врачей."""
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_doctor(request.user):
            raise PermissionDenied
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
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
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
        except ImportError:
            # Skip real-time update if channels is not available
            pass
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
            working_days = form.cleaned_data['working_days']
            duration = specialist.service.duration_minutes
            work_start = specialist.work_start
            work_end = specialist.work_end
            
            today = timezone.now().date()
            created_count = 0
            
            from datetime import datetime, timedelta
            
            for day_offset in range(days):
                current_date = today + timedelta(days=day_offset)
                
                # Проверяем, является ли день рабочим (0-Пн, 6-Вс)
                if str(current_date.weekday()) not in working_days:
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
    })

@doctor_required
def doctor_manage_slots_view(request):
    """Страница управления всеми доступными слотами врача (просмотр и удаление)."""
    specialist = request.user.specialist_profile
    # Показываем только свободные слоты на сегодня и будущее
    today = timezone.now().date()
    slots = TimeSlot.objects.filter(
        specialist=specialist,
        date__gte=today,
        is_available=True
    ).order_by('date', 'time')
    
    return render(request, 'doctor/doctor_manage_slots.html', {
        'slots': slots,
    })

@doctor_required
def doctor_delete_slot_view(request, slot_id):
    """Удаление конкретного свободного слота врачом."""
    specialist = request.user.specialist_profile
    slot = get_object_or_404(TimeSlot, pk=slot_id, specialist=specialist, is_available=True)
    
    # Можно удалять только те слоты, на которые никто не записан
    # (Хотя is_available=True уже это гарантирует в нашей логике)
    slot.delete()
    messages.success(request, 'Временной слот успешно удален.')
    return redirect('doctor_manage_slots')

@doctor_required
def doctor_bulk_actions_view(request):
    """Групповые действия над слотами (удаление, изменение даты)."""
    if request.method == 'POST':
        action = request.POST.get('action')
        slot_ids = request.POST.getlist('slot_ids')
        specialist = request.user.specialist_profile
        
        if not slot_ids:
            messages.warning(request, 'Ни один слот не выбран.')
            return redirect('doctor_manage_slots')
            
        slots = TimeSlot.objects.filter(pk__in=slot_ids, specialist=specialist, is_available=True)
        count = slots.count()
        
        if action == 'delete':
            slots.delete()
            messages.success(request, f'Успешно удалено {count} слотов.')
            
        elif action == 'change_date':
            new_date = request.POST.get('new_date')
            if not new_date:
                messages.error(request, 'Дата для переноса не указана.')
                return redirect('doctor_manage_slots')
            
            updated_count = 0
            skipped_count = 0
            for slot in slots:
                # Проверяем на конфликт перед перемещением
                if TimeSlot.objects.filter(specialist=specialist, date=new_date, time=slot.time).exclude(pk=slot.id).exists():
                    skipped_count += 1
                else:
                    slot.date = new_date
                    slot.save()
                    updated_count += 1
            
            msg = f'Перенесено {updated_count} слотов на {new_date}.'
            if skipped_count:
                msg += f' Пропущено {skipped_count} из-за конфликтов времени.'
            messages.success(request, msg)
            
    return redirect('doctor_manage_slots')

@doctor_required
def doctor_edit_slot_view(request, slot_id):
    """Редактирование существующего свободного слота (изменение даты или времени)."""
    specialist = request.user.specialist_profile
    slot = get_object_or_404(TimeSlot, pk=slot_id, specialist=specialist, is_available=True)
    
    if request.method == 'POST':
        form = ManualSlotForm(request.POST)
        if form.is_valid():
            new_date = form.cleaned_data['date']
            new_time = form.cleaned_data['time']
            
            # Проверяем на конфликт (чтобы не было двух одинаковых слотов)
            if TimeSlot.objects.filter(specialist=specialist, date=new_date, time=new_time).exclude(pk=slot.id).exists():
                messages.error(request, f'Слот на {new_date} {new_time} уже существует!')
            else:
                slot.date = new_date
                slot.time = new_time
                slot.save()
                messages.success(request, 'Время слота успешно изменено!')
                return redirect('doctor_manage_slots')
    else:
        form = ManualSlotForm(initial={'date': slot.date, 'time': slot.time})
        
    return render(request, 'doctor/doctor_edit_slot.html', {'form': form, 'slot': slot})

@doctor_required
def doctor_add_manual_slot_view(request):
    """Страница для ручного добавления единичного свободного слота врачом."""
    specialist = request.user.specialist_profile
    
    if request.method == 'POST':
        form = ManualSlotForm(request.POST)
        if form.is_valid():
            slot_date = form.cleaned_data['date']
            slot_time = form.cleaned_data['time']
            
            slot, created = TimeSlot.objects.get_or_create(
                specialist=specialist,
                date=slot_date,
                time=slot_time,
                defaults={'is_available': True}
            )
            
            if created:
                messages.success(request, f'Свободное время на {slot_date} {slot_time} успешно добавлено!')
            else:
                messages.warning(request, f'Слот на {slot_date} {slot_time} уже существует.')
                
            return redirect('doctor_dashboard')
    else:
        # Default to today
        import datetime
        form = ManualSlotForm(initial={'date': datetime.date.today(), 'time': '12:00'})
        
    return render(request, 'doctor/doctor_add_manual_slot.html', {'form': form})


# ═══════════════════════════════════════════════════════════════════════════════
# ─── ADMIN PANEL VIEWS ───────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def is_admin_user(user):
    return user.is_authenticated and user.is_active and (user.is_staff or user.is_superuser)


def admin_required(view_func):
    """Декоратор: доступ только для is_staff / superuser."""
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_admin_user(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


@admin_required
def admin_dashboard_view(request):
    """Главный дашборд администратора."""
    from accounts.models import CustomUser
    today = timezone.now().date()
    week_ago = today - timezone.timedelta(days=7)

    # ── Stats ──
    today_count = Appointment.objects.filter(time_slot__date=today).count()
    total_patients = CustomUser.objects.filter(is_doctor=False, is_staff=False, is_superuser=False).count()
    total_specialists = Specialist.objects.count()
    active_specialists = Specialist.objects.filter(is_active=True).count()
    total_appointments = Appointment.objects.count()
    week_total = Appointment.objects.filter(time_slot__date__gte=week_ago).count()

    # ── Status breakdown ──
    status_stats = list(Appointment.objects.values('status').annotate(count=Count('status')))
    status_data = {item['status']: item['count'] for item in status_stats}

    # ── Recent appointments ──
    recent_appointments = Appointment.objects.select_related(
        'patient', 'specialist', 'service', 'time_slot'
    ).order_by('-created_at')[:10]

    # ── Recent user registrations ──
    recent_users = CustomUser.objects.filter(
        is_doctor=False, is_staff=False, is_superuser=False
    ).order_by('-date_joined')[:5]

    # ── Line chart: last 7 days ──
    days_list = []
    counts_list = []
    for i in range(6, -1, -1):
        d = today - timezone.timedelta(days=i)
        days_list.append(f'"{d.strftime("%d.%m")}"')
        counts_list.append(Appointment.objects.filter(time_slot__date=d).count())

    # ── Top specialists by appointment count ──
    top_raw = (
        Specialist.objects.filter(is_active=True)
        .annotate(appt_count=Count('appointments'))
        .order_by('-appt_count')[:5]
    )
    max_count = top_raw[0].appt_count if top_raw else 1
    top_specialists = [
        {
            'specialist': s,
            'count': s.appt_count,
            'pct': int(s.appt_count / max_count * 100) if max_count else 0,
        }
        for s in top_raw
    ]

    # ── ЛЕНТА СОБЫТИЙ (Notification Center) ──
    activities = []
    
    # 1. Последние записи
    recent_apps = Appointment.objects.select_related('patient', 'specialist', 'service', 'time_slot').order_by('-created_at')[:10]
    for app in recent_apps:
        activities.append({
            'type': 'appointment',
            'icon': 'bi-calendar-plus',
            'color': 'primary',
            'title': 'Новая запись',
            'text': f'Пациент {app.patient.get_full_name()} записался к врачу {app.specialist.last_name} ({app.service.name})',
            'time': app.created_at,
            'status': app.get_status_display()
        })
        
    # 2. Последние отзывы
    recent_reviews = Review.objects.select_related('patient', 'specialist').order_by('-created_at')[:5]
    for rev in recent_reviews:
        activities.append({
            'type': 'review',
            'icon': 'bi-star-fill',
            'color': 'warning',
            'title': 'Новый отзыв',
            'text': f'Пациент {rev.patient.get_full_name()} оставил отзыв врачу {rev.specialist.last_name}: "{rev.comment[:50]}..." ({rev.rating}★)',
            'time': rev.created_at
        })
        
    # 3. Последние отпуска/отсутствия
    recent_absences = SpecialistAbsence.objects.select_related('specialist').order_by('-created_at')[:5]
    for abs_obj in recent_absences:
        activities.append({
            'type': 'absence',
            'icon': 'bi-calendar-x',
            'color': 'danger',
            'title': 'Отсутствие врача',
            'text': f'Врач {abs_obj.specialist.get_full_name()} будет отсутствовать с {abs_obj.start_date.strftime("%d.%m")} по {abs_obj.end_date.strftime("%d.%m")} (Причина: {abs_obj.reason or "Не указана"})',
            'time': abs_obj.created_at
        })

    # 4. Последние регистрации пользователей
    for u in recent_users:
        activities.append({
            'type': 'registration',
            'icon': 'bi-person-plus-fill',
            'color': 'success',
            'title': 'Новый пациент',
            'text': f'Пользователь {u.get_full_name()} (Логин: {u.username}) зарегистрировался в системе',
            'time': u.date_joined,
            'status': 'Активен' if u.is_active else 'Ожидает подтв.'
        })

    # Сортируем всё по времени (от новых к старым)
    activities.sort(key=lambda x: x['time'], reverse=True)
    activities = activities[:15]

    return render(request, 'admin_panel/dashboard.html', {
        'today_count': today_count,
        'total_patients': total_patients,
        'total_specialists': total_specialists,
        'active_specialists': active_specialists,
        'total_appointments': total_appointments,
        'week_total': week_total,
        'status_data': status_data,
        'recent_appointments': recent_appointments,
        'recent_users': recent_users,
        'days_list': '[' + ','.join(days_list) + ']',
        'counts_list': counts_list,
        'top_specialists': top_specialists,
        'activities': activities,
    })


@admin_required
def admin_appointments_view(request):
    """Все записи с фильтрацией."""
    today = timezone.now().date()
    selected_date = request.GET.get('date', '')
    specialist_id = request.GET.get('specialist', '')
    status_filter = request.GET.get('status', '')

    qs = Appointment.objects.select_related('patient', 'specialist', 'service', 'time_slot')

    if selected_date:
        import datetime
        try:
            filter_date = datetime.date.fromisoformat(selected_date)
            qs = qs.filter(time_slot__date=filter_date)
        except ValueError:
            selected_date = ''
    if specialist_id:
        qs = qs.filter(specialist_id=specialist_id)
    if status_filter:
        qs = qs.filter(status=status_filter)

    qs = qs.order_by('-time_slot__date', 'time_slot__time')
    paginator = Paginator(qs, 25)
    appointments = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'admin_panel/appointments.html', {
        'appointments': appointments,
        'specialists': Specialist.objects.filter(is_active=True),
        'selected_date': selected_date,
        'selected_specialist': specialist_id,
        'selected_status': status_filter,
        'status_choices': Appointment.STATUS_CHOICES,
    })

@admin_required
@require_POST
def admin_delete_appointment_view(request, appointment_id):
    """Физическое удаление записи из базы данных."""
    appointment = get_object_or_404(Appointment, pk=appointment_id)
    
    # Если запись еще не отменена и не завершена, освобождаем слот
    if appointment.status in ['pending', 'confirmed']:
        appointment.time_slot.is_available = True
        appointment.time_slot.save()
        
    num = appointment.queue_number
    appointment.delete()
    
    messages.success(request, f'Запись #{num} была полностью удалена из базы.')
    return redirect(request.POST.get('next', 'admin_appointments'))


@admin_required
def admin_specialists_view(request):
    """Управление врачами."""
    specialists = Specialist.objects.select_related('service').prefetch_related('appointments', 'reviews').all()
    return render(request, 'admin_panel/specialists.html', {'specialists': specialists})


@admin_required
def admin_toggle_specialist_view(request, specialist_id):
    """Активировать / деактивировать врача."""
    specialist = get_object_or_404(Specialist, pk=specialist_id)
    specialist.is_active = not specialist.is_active
    specialist.save()
    state = 'активирован' if specialist.is_active else 'деактивирован'
    messages.success(request, f'Врач {specialist.get_full_name()} {state}.')
    return redirect('admin_specialists')

@admin_required
def admin_edit_specialist_view(request, specialist_id):
    """Редактирование профиля врача."""
    specialist = get_object_or_404(Specialist, pk=specialist_id)
    if request.method == 'POST':
        form = SpecialistForm(request.POST, request.FILES, instance=specialist)
        if form.is_valid():
            form.save()
            # Обновляем CustomUser если он есть
            if specialist.user:
                specialist.user.first_name = specialist.first_name
                specialist.user.last_name = specialist.last_name
                specialist.user.save()
            messages.success(request, f'Данные врача «{specialist.get_full_name()}» успешно обновлены!')
            return redirect('admin_specialists')
    else:
        form = SpecialistForm(instance=specialist)
    
    return render(request, 'admin_panel/specialist_edit.html', {'form': form, 'specialist': specialist})

@admin_required
@require_POST
def admin_delete_specialist_view(request, specialist_id):
    """Удаление врача и его аккаунта."""
    specialist = get_object_or_404(Specialist, pk=specialist_id)
    name = specialist.get_full_name()
    user = specialist.user
    specialist.delete()
    if user:
        user.delete()
    messages.success(request, f'Врач «{name}» и его аккаунт пользователя удалены.')
    return redirect('admin_specialists')


@admin_required
def admin_services_view(request):
    """Управление услугами."""
    services = Service.objects.prefetch_related('specialists', 'appointments').order_by('name')
    return render(request, 'admin_panel/services.html', {'services': services})

@admin_required
def admin_add_service_view(request):
    """Добавление новой услуги."""
    if request.method == 'POST':
        form = ServiceForm(request.POST)
        if form.is_valid():
            service = form.save()
            messages.success(request, f'Услуга «{service.name}» успешно добавлена!')
            return redirect('admin_services')
    else:
        form = ServiceForm(initial={'icon': 'bi-asterisk', 'duration_minutes': 30})
    
    return render(request, 'admin_panel/service_add.html', {'form': form, 'edit_mode': False})

@admin_required
def admin_edit_service_view(request, service_id):
    """Редактирование услуги."""
    service = get_object_or_404(Service, pk=service_id)
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, f'Услуга «{service.name}» успешно обновлена!')
            return redirect('admin_services')
    else:
        form = ServiceForm(instance=service)
    
    return render(request, 'admin_panel/service_add.html', {'form': form, 'edit_mode': True})

@admin_required
@require_POST
def admin_delete_service_view(request, service_id):
    """Удаление услуги."""
    service = get_object_or_404(Service, pk=service_id)
    name = service.name
    service.delete()
    messages.success(request, f'Услуга «{name}» удалена.')
    return redirect('admin_services')


@admin_required
def admin_toggle_service_view(request, service_id):
    """Показать / скрыть услугу."""
    service = get_object_or_404(Service, pk=service_id)
    service.is_active = not service.is_active
    service.save()
    state = 'активирована' if service.is_active else 'скрыта'
    messages.success(request, f'Услуга «{service.name}» {state}.')
    return redirect('admin_services')


@admin_required
def admin_users_view(request):
    """Список пациентов."""
    from accounts.models import CustomUser
    search_query = request.GET.get('q', '').strip()

    qs = CustomUser.objects.filter(
        is_doctor=False, is_staff=False, is_superuser=False
    ).prefetch_related('appointments').order_by('-date_joined')

    if search_query:
        qs = qs.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    paginator = Paginator(qs, 20)
    users = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'admin_panel/users.html', {
        'users': users,
        'search_query': search_query,
    })


@admin_required
def admin_toggle_user_view(request, user_id):
    """Блокировка / разблокировка пользователя."""
    from accounts.models import CustomUser
    user = get_object_or_404(CustomUser, pk=user_id)
    
    # Не даем админу заблокировать самого себя
    if user == request.user:
        messages.error(request, 'Вы не можете заблокировать самого себя!')
        return redirect('admin_users')
        
    user.is_active = not user.is_active
    user.save()
    
    status = 'разблокирован' if user.is_active else 'заблокирован'
    messages.success(request, f'Пользователь {user.get_full_name()} успешно {status}.')
    return redirect('admin_users')


@admin_required
@require_POST
def admin_delete_user_view(request, user_id):
    """Полное удаление пользователя из базы."""
    from accounts.models import CustomUser
    user = get_object_or_404(CustomUser, pk=user_id)
    
    if user == request.user:
        messages.error(request, 'Вы не можете удалить самого себя!')
        return redirect('admin_users')
        
    name = user.get_full_name()
    user.delete()
    
    messages.success(request, f'Пользователь {name} удален из системы.')
    return redirect('admin_users')


@admin_required
def admin_user_change_password_view(request, user_id):
    """Смена пароля пользователя администратором."""
    from accounts.models import CustomUser
    from django.contrib.auth.forms import SetPasswordForm
    
    user = get_object_or_404(CustomUser, pk=user_id)
    
    if request.method == 'POST':
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Пароль для пользователя {user.get_full_name()} (ЛОГИН: {user.username}) успешно изменен!')
            return redirect('admin_users')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = SetPasswordForm(user)
    
    return render(request, 'admin_panel/user_password_change.html', {
        'form': form,
        'target_user': user
    })


@admin_required
def admin_specialist_absence_view(request, specialist_id):
    """Управление отсутствием специалиста (отпуск, больничный)."""
    specialist = get_object_or_404(Specialist, pk=specialist_id)
    absences = SpecialistAbsence.objects.filter(specialist=specialist).order_by('-start_date')
    
    if request.method == 'POST':
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason', '')
        
        if start_date and end_date:
            # Создаем запись об отсутствии
            absence = SpecialistAbsence.objects.create(
                specialist=specialist,
                start_date=start_date,
                end_date=end_date,
                reason=reason
            )
            
            # БЛОКИРОВКА СЛОТОВ И ОТМЕНА ЗАПИСЕЙ
            # Находим затронутые слоты
            slots = TimeSlot.objects.filter(
                specialist=specialist,
                date__range=[start_date, end_date]
            )
            
            affected_appointments = 0
            for slot in slots:
                if not slot.is_available:
                   # Если есть запись на этот слот - отменяем её
                   if hasattr(slot, 'appointment'):
                       app = slot.appointment
                       app.status = 'cancelled'
                       app.save()
                       affected_appointments += 1
                
                slot.is_available = False
                slot.save()
            
            msg = f'Отсутствие врача успешно добавлено. Заблокировано слотов: {slots.count()}.'
            if affected_appointments > 0:
                msg += f' Автоматически отменено записей: {affected_appointments}.'
            
            messages.success(request, msg)
            return redirect('admin_specialist_absence', specialist_id=specialist_id)
        else:
            messages.error(request, 'Необходимо указать обе даты.')
            
    return render(request, 'admin_panel/specialist_absence.html', {
        'specialist': specialist,
        'absences': absences
    })


@admin_required
@require_POST
def admin_delete_absence_view(request, absence_id):
    """Удаление записи об отсутствии и восстановление слотов."""
    absence = get_object_or_404(SpecialistAbsence, pk=absence_id)
    specialist = absence.specialist
    
    # Восстанавливаем слоты (только те, на которых нет отмененных записей, 
    # чтобы не запутаться, либо просто все делаем доступными)
    slots = TimeSlot.objects.filter(
        specialist=specialist,
        date__range=[absence.start_date, absence.end_date]
    )
    
    for slot in slots:
        # Если на слоте есть запись (даже отмененная), не делаем его доступным автоматически
        if not hasattr(slot, 'appointment'):
            slot.is_available = True
            slot.save()
            
    absence.delete()
    messages.success(request, 'Запись об отсутствии удалена. Свободные слоты восстановлены.')
    return redirect('admin_specialist_absence', specialist_id=specialist.id)


@admin_required
def admin_reviews_view(request):
    """Все отзывы."""
    reviews = Review.objects.select_related('patient', 'specialist').order_by('-created_at')
    total_reviews = reviews.count()
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    five_star_count = reviews.filter(rating=5).count()

    return render(request, 'admin_panel/reviews.html', {
        'reviews': reviews,
        'total_reviews': total_reviews,
        'avg_rating': avg_rating,
        'five_star_count': five_star_count,
    })


@admin_required
@require_POST
def admin_delete_review_view(request, review_id):
    """Удалить отзыв."""
    review = get_object_or_404(Review, pk=review_id)
    review.delete()
    messages.success(request, 'Отзыв удалён.')
    return redirect('admin_reviews')


def custom_404_view(request, exception=None):
    """Принудительный показ премиальной страницы 404 (даже при DEBUG=True)."""
    return render(request, '404.html', status=404)
