from django.core.management.base import BaseCommand
from django.utils import timezone
from queue_app.models import Appointment
from django.core.mail import send_mail
from django.conf import settings
import datetime

class Command(BaseCommand):
    help = 'Отправка email-напоминаний о предстоящих приемах'

    def handle(self, *args, **options):
        tomorrow = timezone.now().date() + datetime.timedelta(days=1)
        
        # Ищем подтвержденные записи на завтра
        appointments = Appointment.objects.filter(
            time_slot__date=tomorrow,
            status='confirmed'
        ).select_related('patient', 'specialist', 'time_slot', 'service')

        count = 0
        for appt in appointments:
            if not appt.patient.email:
                continue
                
            subject = 'Напоминание о приеме — МедЗапись'
            body = (
                f'Здравствуйте, {appt.patient.get_full_name()}!\n\n'
                f'Напоминаем, что завтра ({appt.time_slot.date.strftime("%d.%m.%Y")}) '
                f'у вас запланирован прием:\n\n'
                f'Врач: {appt.specialist.get_full_name()}\n'
                f'Услуга: {appt.service.name}\n'
                f'Время: {appt.time_slot.time.strftime("%H:%M")}\n'
                f'Кабинет: {appt.specialist.cabinet or "в регистратуре"}\n\n'
                f'Пожалуйста, приходите за 10 минут до начала.\n'
                f'Если вы не сможете прийти, пожалуйста, отмените запись в личном кабинете.\n\n'
                f'С уважением, клиника МедЗапись.'
            )
            
            try:
                send_mail(
                    subject,
                    body,
                    getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@medzapis.kz'),
                    [appt.patient.email],
                    fail_silently=True,
                )
                count += 1
            except Exception as e:
                self.stderr.write(f"Ошибка при отправке: {e}")

        self.stdout.write(self.style.SUCCESS(f'Успешно отправлено {count} напоминаний.'))
