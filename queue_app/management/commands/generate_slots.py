"""
Команда: python manage.py generate_slots --days 14
Автоматически генерирует временные слоты для всех активных специалистов.
"""
import argparse
from datetime import date, timedelta, datetime, time
from django.core.management.base import BaseCommand
from queue_app.models import Specialist, TimeSlot


class Command(BaseCommand):
    help = 'Генерирует временные слоты для всех активных специалистов на N дней вперёд'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Количество дней для генерации слотов (по умолчанию 7)'
        )
        parser.add_argument(
            '--specialist',
            type=int,
            default=None,
            help='ID конкретного специалиста (по умолчанию — все активные)'
        )

    def handle(self, *args, **options):
        days = options['days']
        specialist_id = options['specialist']

        if specialist_id:
            specialists = Specialist.objects.filter(pk=specialist_id, is_active=True)
            if not specialists.exists():
                self.stdout.write(self.style.ERROR(f'Специалист с ID={specialist_id} не найден или не активен.'))
                return
        else:
            specialists = Specialist.objects.filter(is_active=True).select_related('service')

        if not specialists.exists():
            self.stdout.write(self.style.WARNING('Нет активных специалистов.'))
            return

        today = date.today()
        created_total = 0
        skipped_total = 0

        for specialist in specialists:
            duration = specialist.service.duration_minutes
            work_start = specialist.work_start
            work_end = specialist.work_end

            self.stdout.write(
                f'\n📅 {specialist.get_full_name()} | {work_start}–{work_end} | каждые {duration} мин.'
            )

            for day_offset in range(days):
                current_date = today + timedelta(days=day_offset)

                # Пропускаем воскресенье (weekday=6) и субботу (weekday=5)
                if current_date.weekday() >= 5:
                    continue

                # Пропускаем дни отсутствия специалиста (отпуск, больничный)
                if specialist.absences.filter(
                    start_date__lte=current_date,
                    end_date__gte=current_date
                ).exists():
                    self.stdout.write(f'  ⏭️  {current_date} — отсутствие, пропускаем.')
                    continue

                current_time = datetime.combine(current_date, work_start)
                end_time = datetime.combine(current_date, work_end)

                while current_time < end_time:
                    slot_time = current_time.time()

                    slot, created = TimeSlot.objects.get_or_create(
                        specialist=specialist,
                        date=current_date,
                        time=slot_time,
                        defaults={'is_available': True}
                    )

                    if created:
                        created_total += 1
                    else:
                        skipped_total += 1

                    current_time += timedelta(minutes=duration)

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Готово! Создано слотов: {created_total} | Уже существовало: {skipped_total}'
        ))
