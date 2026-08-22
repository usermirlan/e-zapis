import json
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q, Avg, Count, Prefetch
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView, View, CreateView, UpdateView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator

from .models import (
    Service, Specialist, TimeSlot, Appointment, Review, Notification,
    SpecialistAbsence, FavoriteSpecialist, ClinicSetting, MedicalRecord,
    PromoCode, WaitingList, PatientPenalty, AuditLog, MedicalAttachment, WhatsAppTemplate
)
from .forms import BookingForm, ServiceForm, SpecialistForm, ReviewForm, MedicalRecordForm, SlotGenerationForm, ManualSlotForm
from accounts.forms import DoctorRegisterForm, RegisterForm
from accounts.models import CustomUser

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

    today = timezone.now().date()
    now = timezone.now()

    # Динамический расчет времени ожидания
    active_appointments = Appointment.objects.filter(
        time_slot__date=today,
        status__in=['pending', 'confirmed']
    ).count()

    if specialists_count > 0:
        wait_time = (active_appointments // specialists_count) * 10
    else:
        wait_time = 0

    # Записей сегодня
    today_appointments_count = Appointment.objects.filter(
        time_slot__date=today
    ).count()

    # Ближайший приём (следующий подтверждённый слот)
    next_slot = TimeSlot.objects.filter(
        date=today,
        is_available=False,
        time__gte=now.time()
    ).order_by('time').first()

    return render(request, 'queue_app/home.html', {
        'services': services,
        'specialists': Specialist.objects.filter(is_active=True).select_related('service').annotate(avg_rating=Avg('reviews__rating'))[:6],
        'specialists_count': specialists_count,
        'appointments_count': appointments_count,
        'wait_time': wait_time,
        'today_appointments_count': today_appointments_count,
        'next_slot': next_slot,
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

    specialist = get_object_or_404(
        Specialist.objects.annotate(avg_rating=Avg('reviews__rating')).prefetch_related('reviews'),
        pk=specialist_id,
        is_active=True
    )

    today = timezone.now().date()

    # ── Отсутствия (отпуск, больничный) специалиста ──
    absences = SpecialistAbsence.objects.filter(
        specialist=specialist,
        end_date__gte=today
    )

    # Собираем даты, когда специалист отсутствует
    absent_dates = set()
    for absence in absences:
        current = absence.start_date
        while current <= absence.end_date:
            if current >= today:
                absent_dates.add(current)
            import datetime
            current += datetime.timedelta(days=1)

    available_slots = TimeSlot.objects.filter(
        specialist=specialist,
        is_available=True,
        date__gte=today
    ).exclude(
        date__in=absent_dates  # Исключаем слоты в период отсутствия
    ).order_by('date', 'time')

    slots_by_date = {}
    for slot in available_slots:
        date_key = slot.date
        if date_key not in slots_by_date:
            slots_by_date[date_key] = []
        slots_by_date[date_key].append(slot)

    is_favorite = False
    if request.user.is_authenticated and not request.user.is_doctor:
        is_favorite = FavoriteSpecialist.objects.filter(user=request.user, specialist=specialist).exists()

    return render(request, 'queue_app/specialist_detail.html', {
        'specialist': specialist,
        'slots_by_date': slots_by_date,
        'today': today,
        'absent_dates': sorted(absent_dates),
        'is_favorite': is_favorite,
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


@login_required
def certificate_view(request, appointment_id):
    """Страница для просмотра и печати медицинской справки (протокола)."""
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
    
    if not hasattr(appointment, 'medical_record'):
        messages.error(request, 'Для этого приема еще нет медицинской справки.')
        return redirect('my_appointments')

    return render(request, 'queue_app/certificate.html', {
        'appointment': appointment,
        'record': appointment.medical_record
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
    search_query = request.GET.get('q', '').strip()
    
    qs = Specialist.objects.filter(is_active=True).select_related('service')

    if service_id:
        qs = qs.filter(service_id=service_id)
        
    if search_query:
        qs = qs.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(middle_name__icontains=search_query) |
            Q(service__name__icontains=search_query)
        )

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


@login_required
@require_POST
def api_toggle_favorite(request):
    if request.user.is_doctor:
        return JsonResponse({'error': 'Врачи не могут добавлять в избранное'}, status=403)
        
    specialist_id = request.POST.get('specialist_id')
    specialist = get_object_or_404(Specialist, id=specialist_id)
    
    fav, created = FavoriteSpecialist.objects.get_or_create(user=request.user, specialist=specialist)
    if not created:
        fav.delete()
        is_favorite = False
    else:
        is_favorite = True
        
    return JsonResponse({'is_favorite': is_favorite})


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
        
        work_start = request.POST.get('work_start')
        if work_start:
            specialist.work_start = work_start
            
        work_end = request.POST.get('work_end')
        if work_end:
            specialist.work_end = work_end
            
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


@login_required
def favorites_view(request):
    if request.user.is_doctor:
        return redirect('doctor_dashboard')
        
    favorites = FavoriteSpecialist.objects.filter(user=request.user).select_related('specialist__service')
    specialists = [f.specialist for f in favorites]
    
    return render(request, 'queue_app/favorites.html', {
        'specialists': specialists,
    })


# ─── НОВЫЕ АДМИН-ФУНКЦИИ ───────────────────────────────────────────────────

@admin_required
def admin_settings_view(request):
    """Управление настройками клиники."""
    settings_obj = ClinicSetting.get_settings()
    if request.method == 'POST':
        settings_obj.clinic_name = request.POST.get('clinic_name', settings_obj.clinic_name)
        settings_obj.phone = request.POST.get('phone', settings_obj.phone)
        settings_obj.email = request.POST.get('email', settings_obj.email)
        settings_obj.address = request.POST.get('address', settings_obj.address)
        settings_obj.work_hours = request.POST.get('work_hours', settings_obj.work_hours)
        settings_obj.whatsapp_number = request.POST.get('whatsapp_number', settings_obj.whatsapp_number)
        settings_obj.instagram_url = request.POST.get('instagram_url', '')
        settings_obj.telegram_url = request.POST.get('telegram_url', '')
        settings_obj.save()
        messages.success(request, 'Настройки клиники успешно сохранены!')
        return redirect('admin_settings')

    return render(request, 'admin_panel/settings.html', {'settings': settings_obj})


@admin_required
def admin_generate_slots_view(request):
    """Массовая генерация слотов врачей."""
    specialists = Specialist.objects.filter(is_active=True)
    if request.method == 'POST':
        spec_id = request.POST.get('specialist_id')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        duration = int(request.POST.get('duration', 30))
        work_start = request.POST.get('work_start', '09:00')
        work_end = request.POST.get('work_end', '18:00')
        skip_weekends = request.POST.get('skip_weekends') == 'on'

        if not start_date_str or not end_date_str:
            messages.error(request, 'Укажите начальную и конечную дату.')
            return redirect('admin_generate_slots')

        try:
            start_d = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_d = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            start_t = datetime.strptime(work_start, '%H:%M').time()
            end_t = datetime.strptime(work_end, '%H:%M').time()
        except ValueError:
            messages.error(request, 'Неверный формат даты или времени.')
            return redirect('admin_generate_slots')

        target_specs = specialists if spec_id == 'all' else specialists.filter(id=spec_id)
        created_count = 0

        current_d = start_d
        while current_d <= end_d:
            if skip_weekends and current_d.weekday() >= 5:
                current_d += timedelta(days=1)
                continue

            for spec in target_specs:
                curr_dt = datetime.combine(current_d, start_t)
                end_dt = datetime.combine(current_d, end_t)

                while curr_dt + timedelta(minutes=duration) <= end_dt:
                    slot_time = curr_dt.time()
                    slot, created = TimeSlot.objects.get_or_create(
                        specialist=spec,
                        date=current_d,
                        time=slot_time,
                        defaults={'is_available': True}
                    )
                    if created:
                        created_count += 1
                    curr_dt += timedelta(minutes=duration)

            current_d += timedelta(days=1)

        messages.success(request, f'Успешно создано временных слотов: {created_count}')
        return redirect('admin_generate_slots')

    return render(request, 'admin_panel/generate_slots.html', {'specialists': specialists})


@admin_required
def admin_export_appointments_csv(request):
    """Экспорт записей в Excel/CSV с кодировкой UTF-8 BOM."""
    import csv

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="appointments_export.csv"'
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Талон №', 'Пациент', 'Телефон', 'Врач', 'Услуга', 'Дата', 'Время', 'Кабинет', 'Статус'])

    qs = Appointment.objects.select_related('patient', 'specialist', 'service', 'time_slot').order_by('-created_at')
    for app in qs:
        writer.writerow([
            app.queue_number,
            app.patient.get_full_name(),
            app.patient.phone or app.patient.email,
            app.specialist.get_full_name(),
            app.service.name,
            app.time_slot.date.strftime('%d.%m.%Y'),
            app.time_slot.time.strftime('%H:%M'),
            app.specialist.cabinet or '—',
            app.get_status_display()
        ])

    return response


@admin_required
def admin_export_users_csv(request):
    """Экспорт пациентов в Excel/CSV."""
    import csv
    from accounts.models import CustomUser

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="patients_export.csv"'
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['ID', 'ФИО', 'Логин', 'Телефон', 'Email', 'Дата рождения', 'Дата регистрации', 'Статус'])

    users = CustomUser.objects.filter(is_doctor=False, is_staff=False, is_superuser=False).order_by('-date_joined')
    for u in users:
        writer.writerow([
            u.id,
            u.get_full_name(),
            u.username,
            u.phone or '—',
            u.email or '—',
            u.date_of_birth.strftime('%d.%m.%Y') if u.date_of_birth else '—',
            u.date_joined.strftime('%d.%m.%Y %H:%M'),
            'Активен' if u.is_active else 'Заблокирован'
        ])

    return response


@admin_required
def admin_calendar_view(request):
    """Интерактивный календарь приёмов клиники."""
    selected_date_str = request.GET.get('date', timezone.now().strftime('%Y-%m-%d'))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = timezone.now().date()

    specialists = Specialist.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            'time_slots',
            queryset=TimeSlot.objects.filter(date=selected_date).select_related('appointment__patient', 'appointment__service').order_by('time'),
            to_attr='day_slots'
        )
    )

    return render(request, 'admin_panel/calendar.html', {
        'specialists': specialists,
        'selected_date': selected_date,
        'prev_date': (selected_date - timedelta(days=1)).strftime('%Y-%m-%d'),
        'next_date': (selected_date + timedelta(days=1)).strftime('%Y-%m-%d'),
        'today_date': timezone.now().strftime('%Y-%m-%d')
    })


@admin_required
def admin_user_detail_view(request, user_id):
    """Электронная мед-карта и история пациента."""
    from accounts.models import CustomUser
    patient = get_object_or_404(CustomUser, pk=user_id)
    appointments = Appointment.objects.filter(patient=patient).select_related(
        'specialist', 'service', 'time_slot', 'medical_record'
    ).order_by('-created_at')

    return render(request, 'admin_panel/user_detail.html', {
        'patient': patient,
        'appointments': appointments
    })


@admin_required
def admin_global_search_api(request):
    """Быстрый глобальный поиск (AJAX) — возвращает patients/appointments/specialists."""
    from accounts.models import CustomUser
    from django.urls import reverse

    q = request.GET.get('q', '').strip()
    if not q or len(q) < 2:
        return JsonResponse({'patients': [], 'appointments': [], 'specialists': []})

    # Пациенты
    patients_qs = CustomUser.objects.filter(
        Q(first_name__icontains=q) | Q(last_name__icontains=q) |
        Q(phone__icontains=q) | Q(email__icontains=q),
        is_staff=False, is_superuser=False
    )[:6]
    patients = [
        {
            'name': p.get_full_name() or p.username,
            'phone': getattr(p, 'phone', '') or p.email or '',
            'url': reverse('admin_user_detail', args=[p.id])
        }
        for p in patients_qs
    ]

    # Записи
    apps_qs = Appointment.objects.filter(
        Q(patient__first_name__icontains=q) | Q(patient__last_name__icontains=q) |
        Q(patient__phone__icontains=q)
    ).select_related('patient', 'specialist', 'time_slot')[:6]
    appointments = [
        {
            'patient': a.patient.get_full_name() or a.patient.username,
            'date': a.time_slot.date.strftime('%d.%m.%Y') if a.time_slot else '—',
            'specialist': a.specialist.get_full_name() if a.specialist else '—',
            'url': reverse('admin_appointments')
        }
        for a in apps_qs
    ]

    # Врачи
    specs_qs = Specialist.objects.filter(
        Q(first_name__icontains=q) | Q(last_name__icontains=q) |
        Q(service__name__icontains=q)
    ).select_related('service')[:6]
    specialists = [
        {
            'name': s.get_full_name(),
            'specialty': s.service.name if s.service else '—',
            'url': reverse('admin_edit_specialist', args=[s.id])
        }
        for s in specs_qs
    ]

    return JsonResponse({'patients': patients, 'appointments': appointments, 'specialists': specialists})


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: СЛОТТОРДУ БАШКАРУУ (TIME SLOTS MANAGEMENT)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_slots_view(request):
    """Просмотр, фильтрация и управление всеми временными слотами."""
    specialist_id = request.GET.get('specialist')
    date_filter = request.GET.get('date')
    status_filter = request.GET.get('status')
    
    slots_qs = TimeSlot.objects.select_related('specialist', 'specialist__service', 'appointment', 'appointment__patient').all()
    
    if specialist_id:
        slots_qs = slots_qs.filter(specialist_id=specialist_id)
    if date_filter:
        slots_qs = slots_qs.filter(date=date_filter)
    if status_filter == 'available':
        slots_qs = slots_qs.filter(is_available=True)
    elif status_filter == 'booked':
        slots_qs = slots_qs.filter(is_available=False)
        
    slots_qs = slots_qs.order_by('-date', 'time')
    
    total_slots = TimeSlot.objects.count()
    available_slots = TimeSlot.objects.filter(is_available=True).count()
    booked_slots = total_slots - available_slots
    
    specialists = Specialist.objects.filter(is_active=True).order_by('last_name')
    
    paginator = Paginator(slots_qs, 30)
    page_number = request.GET.get('page')
    slots = paginator.get_page(page_number)
    
    context = {
        'slots': slots,
        'specialists': specialists,
        'selected_specialist': specialist_id,
        'selected_date': date_filter,
        'selected_status': status_filter,
        'total_slots': total_slots,
        'available_slots': available_slots,
        'booked_slots': booked_slots,
    }
    return render(request, 'admin_panel/slots.html', context)


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_add_slot_view(request):
    """Ручное добавление слота админом."""
    if request.method == 'POST':
        specialist_id = request.POST.get('specialist')
        date_val = request.POST.get('date')
        time_val = request.POST.get('time')
        
        if not specialist_id or not date_val or not time_val:
            messages.error(request, 'Пожалуйста, заполните все обязательные поля.')
            return redirect('admin_slots')
            
        specialist = get_object_or_404(Specialist, id=specialist_id)
        
        if TimeSlot.objects.filter(specialist=specialist, date=date_val, time=time_val).exists():
            messages.warning(request, f'Слот на {date_val} {time_val} для врача {specialist.get_full_name()} уже существует!')
        else:
            TimeSlot.objects.create(
                specialist=specialist,
                date=date_val,
                time=time_val,
                is_available=True
            )
            messages.success(request, f'Слот на {date_val} {time_val} для врача {specialist.get_full_name()} успешно добавлен!')
            
    return redirect('admin_slots')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_toggle_slot_view(request, slot_id):
    """Переключение доступности слота."""
    slot = get_object_or_404(TimeSlot, id=slot_id)
    slot.is_available = not slot.is_available
    slot.save()
    status_text = 'доступен для записи' if slot.is_available else 'заблокирован'
    messages.success(request, f'Слот {slot.date} {slot.time} теперь {status_text}.')
    return redirect(request.META.get('HTTP_REFERER', 'admin_slots'))


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_delete_slot_view(request, slot_id):
    """Удаление слота."""
    slot = get_object_or_404(TimeSlot, id=slot_id)
    if hasattr(slot, 'appointment') and slot.appointment:
        messages.error(request, 'Нельзя удалить слот, к которому привязана существующая запись! Сначала отмените запись.')
    else:
        slot.delete()
        messages.success(request, f'Слот {slot.date} {slot.time} удалён.')
    return redirect(request.META.get('HTTP_REFERER', 'admin_slots'))


@login_required
@user_passes_test(is_staff_user, login_url='home')
@require_POST
def admin_bulk_slots_view(request):
    """Массовые действия со слотами (удаление, смена статуса)."""
    action = request.POST.get('action')
    slot_ids = request.POST.getlist('selected_slots')
    
    if not slot_ids:
        messages.warning(request, 'Вы не выбрали ни одного слота.')
        return redirect('admin_slots')
        
    slots_qs = TimeSlot.objects.filter(id__in=slot_ids)
    count = slots_qs.count()
    
    if action == 'delete':
        deleted_count = 0
        for s in slots_qs:
            if not hasattr(s, 'appointment') or not s.appointment:
                s.delete()
                deleted_count += 1
        messages.success(request, f'Удалено {deleted_count} из {count} выбранных слотов (слоты с записями пропущены).')
    elif action == 'make_available':
        slots_qs.update(is_available=True)
        messages.success(request, f'{count} слотов теперь доступны для записи.')
    elif action == 'make_unavailable':
        slots_qs.update(is_available=False)
        messages.success(request, f'{count} слотов заблокированы.')
        
    return redirect('admin_slots')


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: МЕДИЦИНАЛЫК КАРТАЛАР ЖАНА ДИАГНОЗДОР (MEDICAL RECORDS)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_medical_records_view(request):
    """Просмотр и поиск всех медицинских записей и диагнозов."""
    q = request.GET.get('q', '').strip()
    records_qs = MedicalRecord.objects.select_related(
        'appointment', 'appointment__patient', 'appointment__specialist', 'appointment__time_slot', 'appointment__service'
    ).all()
    
    if q:
        records_qs = records_qs.filter(
            Q(diagnosis__icontains=q) |
            Q(recommendations__icontains=q) |
            Q(appointment__patient__first_name__icontains=q) |
            Q(appointment__patient__last_name__icontains=q) |
            Q(appointment__patient__phone__icontains=q) |
            Q(appointment__specialist__last_name__icontains=q)
        )
        
    paginator = Paginator(records_qs, 20)
    page_number = request.GET.get('page')
    records = paginator.get_page(page_number)
    
    return render(request, 'admin_panel/medical_records.html', {
        'records': records,
        'search_query': q,
        'total_count': MedicalRecord.objects.count()
    })


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_delete_medical_record_view(request, record_id):
    """Удаление медицинской записи."""
    record = get_object_or_404(MedicalRecord, id=record_id)
    record.delete()
    messages.success(request, 'Медицинская запись удалена.')
    return redirect('admin_medical_records')


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: УВЕДОМЛЕНИЯ (NOTIFICATIONS)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_notifications_view(request):
    """Просмотр всех уведомлений системы."""
    notifs_qs = Notification.objects.select_related('user', 'appointment').order_by('-created_at')
    
    type_filter = request.GET.get('type')
    if type_filter:
        notifs_qs = notifs_qs.filter(notification_type=type_filter)
        
    paginator = Paginator(notifs_qs, 25)
    page_number = request.GET.get('page')
    notifications = paginator.get_page(page_number)
    
    total_count = Notification.objects.count()
    unread_count = Notification.objects.filter(is_read=False).count()
    
    return render(request, 'admin_panel/notifications.html', {
        'notifications': notifications,
        'total_count': total_count,
        'unread_count': unread_count,
        'type_filter': type_filter
    })


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_delete_notification_view(request, notif_id):
    """Удаление уведомления."""
    notif = get_object_or_404(Notification, id=notif_id)
    notif.delete()
    messages.success(request, 'Уведомление удалено.')
    return redirect('admin_notifications')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_mark_all_notifications_read_view(request):
    """Отметить все уведомления как прочитанные."""
    Notification.objects.filter(is_read=False).update(is_read=True)
    messages.success(request, 'Все уведомления отмечены как прочитанные.')
    return redirect('admin_notifications')


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: КОЛДОНУУЧУЛАРДЫ БАШКАРУУ (USER MANAGEMENT & ROLES)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_add_user_view(request):
    """Создание нового пользователя с выбором роли (Пациент, Врач, Админ)."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        date_of_birth = request.POST.get('date_of_birth') or None
        password = request.POST.get('password', '').strip()
        role = request.POST.get('role', 'patient')
        
        if not username or not email or not password:
            messages.error(request, 'Логин, Email и Пароль обязательны для заполнения.')
            return render(request, 'admin_panel/user_add.html', {'data': request.POST})
            
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, f'Пользователь с логином «{username}» уже существует.')
            return render(request, 'admin_panel/user_add.html', {'data': request.POST})
            
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, f'Пользователь с email «{email}» уже существует.')
            return render(request, 'admin_panel/user_add.html', {'data': request.POST})
            
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            date_of_birth=date_of_birth
        )
        
        if role == 'admin':
            user.is_staff = True
            user.is_superuser = True
        elif role == 'staff':
            user.is_staff = True
        elif role == 'doctor':
            user.is_doctor = True
            
        user.save()
        messages.success(request, f'Пользователь {user.get_full_name() or user.username} успешно создан!')
        return redirect('admin_users')
        
    return render(request, 'admin_panel/user_add.html')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_toggle_user_role_view(request, user_id):
    """Быстрая смена роли пользователя (Врач, Администратор)."""
    user = get_object_or_404(CustomUser, id=user_id)
    role_type = request.GET.get('role')
    
    if role_type == 'doctor':
        user.is_doctor = not user.is_doctor
        user.save()
        status = 'врачом' if user.is_doctor else 'пациентом'
        messages.success(request, f'Пользователь {user.get_full_name()} теперь назначен {status}.')
    elif role_type == 'staff':
        if user == request.user:
            messages.error(request, 'Вы не можете снять права администратора с себя.')
        else:
            user.is_staff = not user.is_staff
            user.save()
            status = 'администратором' if user.is_staff else 'обычным пользователем'
            messages.success(request, f'Статус администратора для {user.get_full_name()} изменён ({status}).')
            
    return redirect(request.META.get('HTTP_REFERER', 'admin_users'))


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: ПРОМОКОДДОР ЖАНА АРЗАНДАТУУЛАР (PROMO CODES)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_promocodes_view(request):
    """Просмотр и создание промокодов."""
    promos = PromoCode.objects.all().order_by('-created_at')
    return render(request, 'admin_panel/promocodes.html', {'promocodes': promos})


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_add_promocode_view(request):
    """Создание нового промокода."""
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        description = request.POST.get('description', '').strip()
        discount_percent = int(request.POST.get('discount_percent') or 0)
        discount_amount = int(request.POST.get('discount_amount') or 0)
        valid_from = request.POST.get('valid_from') or timezone.now().date()
        valid_until = request.POST.get('valid_until')
        max_uses = int(request.POST.get('max_uses') or 100)
        
        if not code or not valid_until:
            messages.error(request, 'Код промокода и срок действия обязательны.')
            return redirect('admin_promocodes')
            
        if PromoCode.objects.filter(code=code).exists():
            messages.error(request, f'Промокод «{code}» уже существует!')
            return redirect('admin_promocodes')
            
        PromoCode.objects.create(
            code=code,
            description=description,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            valid_from=valid_from,
            valid_until=valid_until,
            max_uses=max_uses,
            is_active=True
        )
        messages.success(request, f'Промокод «{code}» успешно создан!')
        
    return redirect('admin_promocodes')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_toggle_promocode_view(request, promo_id):
    """Включение/выключение промокода."""
    promo = get_object_or_404(PromoCode, id=promo_id)
    promo.is_active = not promo.is_active
    promo.save()
    status = 'активен' if promo.is_active else 'деактивирован'
    messages.success(request, f'Промокод {promo.code} теперь {status}.')
    return redirect('admin_promocodes')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_delete_promocode_view(request, promo_id):
    """Удаление промокода."""
    promo = get_object_or_404(PromoCode, id=promo_id)
    promo.delete()
    messages.success(request, f'Промокод {promo.code} удалён.')
    return redirect('admin_promocodes')


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: КЕЗЕК КҮТҮҮ БАРАГЫ (WAITING LIST)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_waiting_list_view(request):
    """Просмотр листа ожидания пациентов."""
    status_filter = request.GET.get('status')
    specialist_id = request.GET.get('specialist')
    
    waiting_qs = WaitingList.objects.select_related('patient', 'specialist', 'specialist__service').all()
    
    if status_filter:
        waiting_qs = waiting_qs.filter(status=status_filter)
    if specialist_id:
        waiting_qs = waiting_qs.filter(specialist_id=specialist_id)
        
    specialists = Specialist.objects.filter(is_active=True).order_by('last_name')
    
    return render(request, 'admin_panel/waiting_list.html', {
        'waiting_list': waiting_qs,
        'specialists': specialists,
        'selected_status': status_filter,
        'selected_specialist': specialist_id,
        'total_waiting': WaitingList.objects.filter(status='waiting').count()
    })


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_update_waiting_status_view(request, waiting_id):
    """Смена статуса в листе ожидания."""
    item = get_object_or_404(WaitingList, id=waiting_id)
    new_status = request.POST.get('status') or request.GET.get('status')
    if new_status in ['waiting', 'notified', 'booked', 'expired']:
        item.status = new_status
        item.save()
        messages.success(request, f'Статус для {item.patient.get_full_name()} обновлён.')
    return redirect('admin_waiting_list')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_delete_waiting_view(request, waiting_id):
    """Удаление из листа ожидания."""
    item = get_object_or_404(WaitingList, id=waiting_id)
    item.delete()
    messages.success(request, 'Запись удалена из листа ожидания.')
    return redirect('admin_waiting_list')


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: КАРА ТИЗМЕ ЖАНА NO-SHOW (BLACKLIST / PENALTIES)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_blacklist_view(request):
    """Список нарушителей и заблокированных пациентов."""
    penalties = PatientPenalty.objects.select_related('patient').all().order_by('-is_blocked', '-missed_count')
    all_users = CustomUser.objects.filter(is_staff=False, is_superuser=False).order_by('first_name')
    return render(request, 'admin_panel/blacklist.html', {
        'penalties': penalties,
        'users': all_users,
        'blocked_count': PatientPenalty.objects.filter(is_blocked=True).count()
    })


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_toggle_block_patient_view(request, penalty_id):
    """Блокировка / разблокировка пациента."""
    penalty = get_object_or_404(PatientPenalty, id=penalty_id)
    penalty.is_blocked = not penalty.is_blocked
    penalty.save()
    status = 'заблокирован и добавлен в чёрный список' if penalty.is_blocked else 'разблокирован'
    messages.success(request, f'Пациент {penalty.patient.get_full_name()} теперь {status}.')
    return redirect('admin_blacklist')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_reset_missed_count_view(request, penalty_id):
    """Сброс счётчика неявок пациента."""
    penalty = get_object_or_404(PatientPenalty, id=penalty_id)
    penalty.missed_count = 0
    penalty.is_blocked = False
    penalty.save()
    messages.success(request, f'Счётчик нарушений для {penalty.patient.get_full_name()} сброшен.')
    return redirect('admin_blacklist')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_add_penalty_view(request):
    """Ручное добавление пациента в список нарушителей."""
    if request.method == 'POST':
        patient_id = request.POST.get('patient')
        reason = request.POST.get('reason', '').strip() or 'Нарушение правил клиники / неявка'
        is_blocked = request.POST.get('is_blocked') == 'on'
        
        patient = get_object_or_404(CustomUser, id=patient_id)
        penalty, created = PatientPenalty.objects.get_or_create(patient=patient)
        penalty.reason = reason
        penalty.is_blocked = is_blocked
        if not created:
            penalty.missed_count += 1
        penalty.save()
        messages.success(request, f'Пациент {patient.get_full_name()} добавлен в список контроля.')
    return redirect('admin_blacklist')


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: ЖУРНАЛ ДЕЙСТВИЙ (AUDIT LOGS)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_audit_logs_view(request):
    """Журнал безопасности и действий администраторов."""
    logs_qs = AuditLog.objects.select_related('user').all().order_by('-created_at')
    
    q = request.GET.get('q')
    if q:
        logs_qs = logs_qs.filter(
            Q(action__icontains=q) |
            Q(details__icontains=q) |
            Q(user__username__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q)
        )
        
    paginator = Paginator(logs_qs, 30)
    page_number = request.GET.get('page')
    logs = paginator.get_page(page_number)
    
    return render(request, 'admin_panel/audit_logs.html', {
        'logs': logs,
        'search_query': q,
        'total_logs': AuditLog.objects.count()
    })


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: WHATSAPP ШАБЛОНДОР (WHATSAPP TEMPLATES)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_whatsapp_templates_view(request):
    """Управление шаблонами WhatsApp сообщений."""
    templates = WhatsAppTemplate.objects.all().order_by('-is_active', 'title')
    return render(request, 'admin_panel/whatsapp_templates.html', {'templates': templates})


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_add_whatsapp_template_view(request):
    """Создание нового шаблона WhatsApp."""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        template_type = request.POST.get('template_type', 'reminder_1d')
        message = request.POST.get('message', '').strip()
        
        if not title or not message:
            messages.error(request, 'Название и текст сообщения обязательны.')
            return redirect('admin_whatsapp_templates')
            
        WhatsAppTemplate.objects.create(
            title=title,
            template_type=template_type,
            message=message,
            is_active=True
        )
        messages.success(request, f'Шаблон «{title}» успешно сохранён!')
        
    return redirect('admin_whatsapp_templates')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_toggle_whatsapp_template_view(request, template_id):
    """Включение/выключение шаблона."""
    tpl = get_object_or_404(WhatsAppTemplate, id=template_id)
    tpl.is_active = not tpl.is_active
    tpl.save()
    status = 'активен' if tpl.is_active else 'выключен'
    messages.success(request, f'Шаблон {tpl.title} теперь {status}.')
    return redirect('admin_whatsapp_templates')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_delete_whatsapp_template_view(request, template_id):
    """Удаление шаблона."""
    tpl = get_object_or_404(WhatsAppTemplate, id=template_id)
    tpl.delete()
    messages.success(request, f'Шаблон {tpl.title} удалён.')
    return redirect('admin_whatsapp_templates')


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN PANEL: МЕДИЦИНАЛЫК ФАЙЛДАР ЖАНА АНАЛИЗДЕР (MEDICAL ATTACHMENTS)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_medical_attachments_view(request):
    """Список всех загруженных медицинских анализов и файлов."""
    type_filter = request.GET.get('type')
    q = request.GET.get('q')
    
    attachments_qs = MedicalAttachment.objects.select_related('patient', 'appointment').all().order_by('-created_at')
    
    if type_filter:
        attachments_qs = attachments_qs.filter(file_type=type_filter)
    if q:
        attachments_qs = attachments_qs.filter(
            Q(title__icontains=q) |
            Q(comment__icontains=q) |
            Q(patient__first_name__icontains=q) |
            Q(patient__last_name__icontains=q)
        )
        
    paginator = Paginator(attachments_qs, 25)
    page_number = request.GET.get('page')
    attachments = paginator.get_page(page_number)
    
    patients = CustomUser.objects.filter(is_staff=False, is_superuser=False).order_by('first_name')
    
    return render(request, 'admin_panel/medical_attachments.html', {
        'attachments': attachments,
        'patients': patients,
        'selected_type': type_filter,
        'search_query': q,
        'total_count': MedicalAttachment.objects.count()
    })


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_upload_attachment_view(request):
    """Загрузка нового анализа / файла администратором или врачом."""
    if request.method == 'POST':
        patient_id = request.POST.get('patient')
        title = request.POST.get('title', '').strip()
        file_type = request.POST.get('file_type', 'analysis')
        comment = request.POST.get('comment', '').strip()
        file = request.FILES.get('file')
        
        if not patient_id or not title or not file:
            messages.error(request, 'Пациент, название и файл обязательны для заполнения.')
            return redirect('admin_medical_attachments')
            
        patient = get_object_or_404(CustomUser, id=patient_id)
        MedicalAttachment.objects.create(
            patient=patient,
            title=title,
            file_type=file_type,
            file=file,
            comment=comment
        )
        messages.success(request, f'Файл «{title}» для пациента {patient.get_full_name()} успешно загружен!')
        
    return redirect('admin_medical_attachments')


@login_required
@user_passes_test(is_staff_user, login_url='home')
def admin_delete_attachment_view(request, attachment_id):
    """Удаление файла анализа."""
    attachment = get_object_or_404(MedicalAttachment, id=attachment_id)
    attachment.delete()
    messages.success(request, 'Медицинский файл удалён.')
    return redirect('admin_medical_attachments')

