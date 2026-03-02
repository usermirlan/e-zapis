"""
Seed data command — ASCII-only output for Windows CP1251 compatibility.
Run: python manage.py seed_data
"""

import os
import sys
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from datetime import date, time, timedelta
from queue_app.models import Service, Specialist, TimeSlot

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

User = get_user_model()


class Command(BaseCommand):
    help = 'Fills the database with test data.'

    def handle(self, *args, **options):
        self.stdout.write('\n--- Seeding database ---\n')

        self._create_superuser()
        services = self._create_services()
        specialists = self._create_specialists(services)
        self._create_time_slots(specialists)

        self.stdout.write(self.style.SUCCESS('\n[OK] Database seeded successfully!\n'))
        self.stdout.write('  Admin login: admin')
        self.stdout.write('  Admin password: Admin1234!')
        self.stdout.write('  Admin panel: http://127.0.0.1:8000/admin/\n')

    def _create_superuser(self):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@clinic.kz',
                password='Admin1234!',
                first_name='Admin',
                last_name='System',
                phone='+7 (777) 000-00-00',
            )
            self.stdout.write(self.style.SUCCESS('  [+] Superuser created: admin / Admin1234!'))
        else:
            self.stdout.write(self.style.WARNING('  [!] Superuser already exists.'))

    def _create_services(self):
        self.stdout.write('\n--- Creating services ---')

        services_data = [
            {
                'name': 'Терапевт',
                'description': 'Первичная медицинская помощь, лечение ОРВИ, гриппа, хронических заболеваний.',
                'icon': 'bi-heart-pulse',
                'duration_minutes': 20,
            },
            {
                'name': 'Педиатр',
                'description': 'Медицинская помощь детям от 0 до 18 лет. Профилактика и лечение.',
                'icon': 'bi-emoji-smile',
                'duration_minutes': 25,
            },
            {
                'name': 'Стоматолог',
                'description': 'Лечение и профилактика заболеваний зубов и полости рта.',
                'icon': 'bi-bandaid',
                'duration_minutes': 45,
            },
            {
                'name': 'Кардиолог',
                'description': 'Диагностика и лечение заболеваний сердечно-сосудистой системы.',
                'icon': 'bi-activity',
                'duration_minutes': 30,
            },
            {
                'name': 'Невролог',
                'description': 'Лечение заболеваний нервной системы: головные боли, остеохондроз.',
                'icon': 'bi-lightning-charge',
                'duration_minutes': 30,
            },
        ]

        created_services = []
        for data in services_data:
            service, created = Service.objects.get_or_create(name=data['name'], defaults=data)
            created_services.append(service)
            tag = '[+]' if created else '[=]'
            self.stdout.write(f'  {tag} Service: {service.name}')

        return created_services

    def _create_specialists(self, services):
        self.stdout.write('\n--- Creating specialists ---')

        service_map = {s.name: s for s in services}

        specialists_data = [
            {
                'first_name': 'Айгуль', 'last_name': 'Смагулова', 'middle_name': 'Берикқызы',
                'service_name': 'Терапевт', 'experience_years': 12, 'cabinet': '101',
                'work_start': time(8, 0), 'work_end': time(16, 0),
                'bio': 'Врач высшей категории, специалист по внутренним болезням.',
            },
            {
                'first_name': 'Данияр', 'last_name': 'Ахметов', 'middle_name': 'Серікұлы',
                'service_name': 'Терапевт', 'experience_years': 7, 'cabinet': '102',
                'work_start': time(10, 0), 'work_end': time(18, 0),
                'bio': 'Специалист по лечению хронических заболеваний.',
            },
            {
                'first_name': 'Гүлнар', 'last_name': 'Бекова', 'middle_name': 'Сержанқызы',
                'service_name': 'Педиатр', 'experience_years': 15, 'cabinet': '201',
                'work_start': time(8, 0), 'work_end': time(14, 0),
                'bio': 'Врач высшей категории. Неонатология и педиатрия раннего возраста.',
            },
            {
                'first_name': 'Нурлан', 'last_name': 'Сейткали', 'middle_name': 'Жанатұлы',
                'service_name': 'Педиатр', 'experience_years': 5, 'cabinet': '202',
                'work_start': time(14, 0), 'work_end': time(20, 0),
                'bio': 'Молодой специалист, стажировка в детской клинике.',
            },
            {
                'first_name': 'Мадина', 'last_name': 'Жаксыбекова', 'middle_name': 'Ерланқызы',
                'service_name': 'Стоматолог', 'experience_years': 10, 'cabinet': '301',
                'work_start': time(9, 0), 'work_end': time(17, 0),
                'bio': 'Имплантология и ортодонтия.',
            },
            {
                'first_name': 'Арман', 'last_name': 'Дауленов', 'middle_name': 'Маратұлы',
                'service_name': 'Стоматолог', 'experience_years': 8, 'cabinet': '302',
                'work_start': time(11, 0), 'work_end': time(19, 0),
                'bio': 'Эстетическая стоматология и отбеливание.',
            },
            {
                'first_name': 'Талгат', 'last_name': 'Нурмагамбетов', 'middle_name': 'Ерікұлы',
                'service_name': 'Кардиолог', 'experience_years': 20, 'cabinet': '401',
                'work_start': time(8, 0), 'work_end': time(14, 0),
                'bio': 'Профессор кардиологии, более 30 научных работ.',
            },
            {
                'first_name': 'Сандугаш', 'last_name': 'Отарбекова', 'middle_name': 'Серікқызы',
                'service_name': 'Невролог', 'experience_years': 9, 'cabinet': '501',
                'work_start': time(9, 0), 'work_end': time(17, 0),
                'bio': 'Мигрень, инсомния, нейропатические боли.',
            },
        ]

        created_specialists = []
        for data in specialists_data:
            service_name = data.pop('service_name')
            service = service_map.get(service_name)
            if not service:
                continue

            specialist, created = Specialist.objects.get_or_create(
                first_name=data['first_name'],
                last_name=data['last_name'],
                defaults={**data, 'service': service}
            )
            created_specialists.append(specialist)
            tag = '[+]' if created else '[=]'
            self.stdout.write(f'  {tag} {specialist.get_full_name()} ({service_name})')

        return created_specialists

    def _create_time_slots(self, specialists):
        self.stdout.write('\n--- Creating time slots ---')

        today = date.today()
        slots_created = 0

        for specialist in specialists:
            for day_offset in range(1, 8):
                slot_date = today + timedelta(days=day_offset)

                # Skip weekends
                if slot_date.weekday() >= 5:
                    continue

                duration = specialist.service.duration_minutes
                current_hour = specialist.work_start.hour
                current_min = specialist.work_start.minute

                while True:
                    slot_time = time(current_hour, current_min)
                    if slot_time >= specialist.work_end:
                        break

                    _, created = TimeSlot.objects.get_or_create(
                        specialist=specialist,
                        date=slot_date,
                        time=slot_time,
                        defaults={'is_available': True}
                    )
                    if created:
                        slots_created += 1

                    total_minutes = current_hour * 60 + current_min + duration
                    current_hour = total_minutes // 60
                    current_min = total_minutes % 60

                    if current_hour >= 24:
                        break

        self.stdout.write(f'  [+] Created {slots_created} time slots')
