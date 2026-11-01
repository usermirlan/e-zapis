"""
Сервисный слой бизнес-логики записи на приём.

Здесь собраны операции, которые должны выполняться атомарно и одинаково
для веб-интерфейса и REST API:

* book_slot()          — бронирование слота с защитой от овербукинга;
* cancel_appointment() — отмена записи с освобождением слота;
* register_no_show()   — учёт неявки и автоматическая блокировка (чёрный список);
* get_active_block()   — проверка, заблокирован ли пациент.
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Appointment, AuditLog, PatientPenalty, Specialist, TimeSlot

# Сколько неявок подряд приводит к блокировке и на какой срок
NO_SHOW_LIMIT = 3
BLOCK_DAYS = 30

ACTIVE_STATUSES = ('pending', 'confirmed', 'arrived', 'in_progress')


class BookingError(Exception):
    """Ошибка бизнес-логики бронирования (сообщение показывается пользователю)."""

    def __init__(self, message, code='error'):
        super().__init__(message)
        self.message = message
        self.code = code


def get_active_block(user):
    """Возвращает запись PatientPenalty, если пациент сейчас заблокирован, иначе None.

    Если срок блокировки (blocked_until) истёк, блокировка снимается автоматически.
    """
    penalty = PatientPenalty.objects.filter(patient=user).first()
    if penalty is None or not penalty.is_blocked:
        return None
    if penalty.blocked_until and penalty.blocked_until <= timezone.now():
        penalty.is_blocked = False
        penalty.missed_count = 0
        penalty.save(update_fields=['is_blocked', 'missed_count', 'updated_at'])
        return None
    return penalty


def book_slot(user, slot_id, complaint=''):
    """Атомарно бронирует временной слот для пациента.

    Защита от овербукинга (race condition) реализована на трёх уровнях:
      1) транзакция transaction.atomic — все изменения применяются целиком или не применяются;
      2) пессимистическая блокировка SELECT ... FOR UPDATE строки врача и строки слота —
         параллельные запросы к одному врачу выполняются строго по очереди
         (это же гарантирует уникальность суточного номера очереди);
      3) ограничение UNIQUE на уровне СУБД (OneToOneField time_slot) — последний барьер:
         при его срабатывании IntegrityError преобразуется в понятную ошибку.
    """
    if get_active_block(user):
        raise BookingError(
            'Онлайн-запись для вашей учётной записи временно заблокирована из-за неявок. '
            'Обратитесь в регистратуру.', code='blocked')

    try:
        with transaction.atomic():
            slot = (TimeSlot.objects.select_for_update()
                    .select_related('specialist__service')
                    .filter(pk=slot_id).first())
            if slot is None:
                raise BookingError('Слот не найден.', code='not_found')

            # Блокируем строку врача: все брони к одному врачу сериализуются
            Specialist.objects.select_for_update().filter(pk=slot.specialist_id).first()

            if not slot.is_available:
                raise BookingError('К сожалению, этот слот уже занят. Выберите другое время.',
                                   code='taken')
            if slot.date < timezone.localdate():
                raise BookingError('Этот слот уже недоступен.', code='past')

            if Appointment.objects.filter(
                patient=user, specialist=slot.specialist,
                time_slot__date=slot.date, status__in=ACTIVE_STATUSES,
            ).exists():
                raise BookingError(
                    f'Вы уже записаны к {slot.specialist.get_full_name()} на '
                    f'{slot.date.strftime("%d.%m.%Y")}. Чтобы изменить запись, '
                    f'сначала отмените предыдущую.', code='duplicate')

            # Слот мог освободиться после отмены: старая отменённая запись всё ещё
            # связана с ним (OneToOne). Фиксируем её в журнале аудита и удаляем.
            old = Appointment.objects.filter(time_slot=slot).first()
            if old is not None:
                if old.status not in ('cancelled', 'no_show'):
                    raise BookingError('К сожалению, этот слот уже занят. Выберите другое время.',
                                       code='taken')
                AuditLog.objects.create(
                    user=user, action='ARCHIVE_CANCELLED',
                    details=(f'Слот #{slot.pk} ({slot.date} {slot.time}) повторно забронирован; '
                             f'отменённая запись №{old.queue_number} пациента '
                             f'{old.patient.get_full_name()} удалена'),
                )
                old.delete()

            appointment = Appointment.objects.create(
                patient=user,
                service=slot.specialist.service,
                specialist=slot.specialist,
                time_slot=slot,
                complaint=complaint or '',
            )
    except IntegrityError:
        raise BookingError('К сожалению, этот слот уже занят. Выберите другое время.', code='taken')

    return appointment


def cancel_appointment(appointment, by_user=None, new_status='cancelled'):
    """Отменяет запись (или отмечает неявку) и освобождает слот. Возвращает True при успехе."""
    with transaction.atomic():
        appt = Appointment.objects.select_for_update().select_related('time_slot').get(pk=appointment.pk)
        if appt.status not in ACTIVE_STATUSES:
            return False
        appt.status = new_status
        appt.save(update_fields=['status', 'updated_at'])
        if new_status == 'cancelled':
            slot = appt.time_slot
            # Освобождаем слот, только если приём ещё не прошёл
            if slot.date >= timezone.localdate():
                slot.is_available = True
                slot.save(update_fields=['is_available'])
    appointment.refresh_from_db()
    return True


def register_no_show(appointment, by_user=None, ip=None):
    """Отмечает неявку пациента и обновляет счётчик в чёрном списке.

    При достижении NO_SHOW_LIMIT неявок пациент автоматически блокируется
    на BLOCK_DAYS дней (онлайн-запись недоступна).
    """
    with transaction.atomic():
        appt = Appointment.objects.select_for_update().get(pk=appointment.pk)
        if appt.status not in ACTIVE_STATUSES:
            return None
        appt.status = 'no_show'
        appt.save(update_fields=['status', 'updated_at'])

        penalty, created = PatientPenalty.objects.select_for_update().get_or_create(
            patient=appt.patient, defaults={'missed_count': 0})
        penalty.missed_count += 1
        penalty.reason = f'Неявка на приём №{appt.queue_number} ({appt.time_slot.date})'
        if penalty.missed_count >= NO_SHOW_LIMIT and not penalty.is_blocked:
            penalty.is_blocked = True
            penalty.blocked_until = timezone.now() + timedelta(days=BLOCK_DAYS)
        penalty.save()

        AuditLog.objects.create(
            user=by_user, action='NO_SHOW', ip_address=ip,
            details=(f'Неявка: {appt.patient.get_full_name()}, запись №{appt.queue_number}; '
                     f'всего неявок {penalty.missed_count}'
                     + ('; пациент заблокирован' if penalty.is_blocked else '')),
        )
    appointment.refresh_from_db()
    return penalty


def get_client_ip(request):
    """IP-адрес клиента (с учётом обратного прокси)."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_action(request, action, details):
    """Запись критического действия в журнал аудита (AuditLog)."""
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    return AuditLog.objects.create(user=user, action=action, details=details,
                                   ip_address=get_client_ip(request))
