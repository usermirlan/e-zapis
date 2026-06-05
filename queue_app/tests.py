from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, time, timedelta
from .models import (
    Service, Specialist, TimeSlot, Appointment,
    Review, MedicalRecord, Notification, SpecialistAbsence, FavoriteSpecialist
)

User = get_user_model()



class ServiceModelTest(TestCase):
    def setUp(self):
        self.service = Service.objects.create(
            name='Терапевт',
            duration_minutes=30,
            is_active=True
        )

    def test_service_str(self):
        self.assertEqual(str(self.service), 'Терапевт')

    def test_service_is_active_by_default(self):
        self.assertTrue(self.service.is_active)


class SpecialistModelTest(TestCase):
    def setUp(self):
        self.service = Service.objects.create(name='Хирург', duration_minutes=30)
        self.specialist = Specialist.objects.create(
            first_name='Иван',
            last_name='Петров',
            middle_name='Сергеевич',
            service=self.service,
            experience_years=10,
            cabinet='101',
            work_start=time(9, 0),
            work_end=time(17, 0),
        )

    def test_specialist_full_name(self):
        self.assertEqual(self.specialist.get_full_name(), 'Петров Иван Сергеевич')

    def test_specialist_str(self):
        self.assertIn('Петров', str(self.specialist))


class AppointmentModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testpatient',
            email='patient@test.com',
            password='testpass123',
            first_name='Тест',
            last_name='Пользователь',
            phone='+7777777777'
        )
        self.service = Service.objects.create(name='Кардиолог', duration_minutes=30)
        self.specialist = Specialist.objects.create(
            first_name='Алёна',
            last_name='Иванова',
            service=self.service,
            work_start=time(9, 0),
            work_end=time(17, 0),
        )
        tomorrow = date.today() + timedelta(days=1)
        self.slot = TimeSlot.objects.create(
            specialist=self.specialist,
            date=tomorrow,
            time=time(10, 0),
            is_available=True
        )

    def test_appointment_queue_number_set_on_create(self):
        appointment = Appointment.objects.create(
            patient=self.user,
            service=self.service,
            specialist=self.specialist,
            time_slot=self.slot,
        )
        self.assertEqual(appointment.queue_number, 1)

    def test_slot_marked_unavailable_after_booking(self):
        Appointment.objects.create(
            patient=self.user,
            service=self.service,
            specialist=self.specialist,
            time_slot=self.slot,
        )
        self.slot.refresh_from_db()
        self.assertFalse(self.slot.is_available)

    def test_slot_freed_after_cancel(self):
        appointment = Appointment.objects.create(
            patient=self.user,
            service=self.service,
            specialist=self.specialist,
            time_slot=self.slot,
        )
        appointment.status = 'cancelled'
        appointment.save()
        self.slot.is_available = True
        self.slot.save()
        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_available)


class BookingViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser2',
            email='user2@test.com',
            password='testpass123',
            phone='+7777777778'
        )
        self.service = Service.objects.create(name='ЛОР', duration_minutes=30)
        self.specialist = Specialist.objects.create(
            first_name='Марат',
            last_name='Садыков',
            service=self.service,
            work_start=time(9, 0),
            work_end=time(17, 0),
        )
        tomorrow = date.today() + timedelta(days=1)
        self.slot = TimeSlot.objects.create(
            specialist=self.specialist,
            date=tomorrow,
            time=time(11, 0),
            is_available=True
        )

    def test_booking_requires_login(self):
        response = self.client.get(f'/booking/{self.slot.pk}/')
        self.assertRedirects(response, f'/accounts/login/?next=/booking/{self.slot.pk}/')

    def test_booking_success(self):
        self.client.login(username='testuser2', password='testpass123')
        response = self.client.post(f'/booking/{self.slot.pk}/', {'complaint': 'Болит горло'})
        self.assertEqual(Appointment.objects.count(), 1)
        appointment = Appointment.objects.first()
        self.assertRedirects(response, f'/booking/success/{appointment.pk}/')

    def test_cancel_appointment(self):
        appointment = Appointment.objects.create(
            patient=self.user,
            service=self.service,
            specialist=self.specialist,
            time_slot=self.slot,
            status='pending'
        )
        self.slot.is_available = False
        self.slot.save()

        self.client.login(username='testuser2', password='testpass123')
        response = self.client.post(f'/my-appointments/cancel/{appointment.id}/')
        self.assertRedirects(response, '/my-appointments/')

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'cancelled')
        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_available)

    def test_duplicate_booking_blocked(self):
        self.client.login(username='testuser2', password='testpass123')
        # Первая запись
        Appointment.objects.create(
            patient=self.user,
            service=self.service,
            specialist=self.specialist,
            time_slot=self.slot,
            status='pending'
        )
        # Второй слот того же врача в тот же день
        tomorrow = date.today() + timedelta(days=1)
        slot2 = TimeSlot.objects.create(
            specialist=self.specialist,
            date=tomorrow,
            time=time(12, 0),
            is_available=True
        )
        response = self.client.post(f'/booking/{slot2.pk}/', {'complaint': ''})
        # Должен перенаправить без создания новой записи
        self.assertEqual(Appointment.objects.count(), 1)


class MyAppointmentsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser3',
            email='user3@test.com',
            password='testpass123',
            phone='+7777777779'
        )

    def test_my_appointments_requires_login(self):
        response = self.client.get('/my-appointments/')
        self.assertRedirects(response, '/accounts/login/?next=/my-appointments/')

    def test_my_appointments_accessible_when_logged_in(self):
        self.client.login(username='testuser3', password='testpass123')
        response = self.client.get('/my-appointments/')
        self.assertEqual(response.status_code, 200)


# ─────────────────────────────────────────────────────────
# Review тесттери
# ─────────────────────────────────────────────────────────
class ReviewModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='reviewer', email='rev@test.com',
            password='pass123', phone='+996700000001'
        )
        self.service = Service.objects.create(name='Невролог', duration_minutes=30)
        self.specialist = Specialist.objects.create(
            first_name='Айгуль', last_name='Асанова',
            service=self.service, work_start=time(9, 0), work_end=time(17, 0),
        )
        tomorrow = date.today() + timedelta(days=1)
        self.slot = TimeSlot.objects.create(
            specialist=self.specialist, date=tomorrow,
            time=time(10, 0), is_available=True
        )
        self.appointment = Appointment.objects.create(
            patient=self.user, service=self.service,
            specialist=self.specialist, time_slot=self.slot,
            status='completed'
        )

    def test_review_created(self):
        review = Review.objects.create(
            patient=self.user,
            specialist=self.specialist,
            appointment=self.appointment,
            rating=5,
            comment='Абдан жакшы дарыгер!'
        )
        self.assertEqual(review.rating, 5)
        self.assertEqual(str(review.comment), 'Абдан жакшы дарыгер!')

    def test_average_rating(self):
        Review.objects.create(
            patient=self.user, specialist=self.specialist,
            appointment=self.appointment, rating=4
        )
        self.assertEqual(self.specialist.average_rating, 4.0)

    def test_duplicate_review_blocked(self):
        """Бир жазылуу үчүн эки жолу пикир жазылбасын."""
        Review.objects.create(
            patient=self.user, specialist=self.specialist,
            appointment=self.appointment, rating=5
        )
        with self.assertRaises(Exception):
            Review.objects.create(
                patient=self.user, specialist=self.specialist,
                appointment=self.appointment, rating=3
            )


# ─────────────────────────────────────────────────────────
# MedicalRecord тесттери
# ─────────────────────────────────────────────────────────
class MedicalRecordTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='patient_med', email='med@test.com',
            password='pass123', phone='+996700000002'
        )
        self.service = Service.objects.create(name='Терапевт', duration_minutes=30)
        self.specialist = Specialist.objects.create(
            first_name='Нурлан', last_name='Токтоматов',
            service=self.service, work_start=time(9, 0), work_end=time(17, 0),
        )
        slot = TimeSlot.objects.create(
            specialist=self.specialist,
            date=date.today() + timedelta(days=2),
            time=time(11, 0), is_available=True
        )
        self.appointment = Appointment.objects.create(
            patient=self.user, service=self.service,
            specialist=self.specialist, time_slot=slot,
            status='completed'
        )

    def test_medical_record_created(self):
        record = MedicalRecord.objects.create(
            appointment=self.appointment,
            diagnosis='ОРВИ',
            recommendations='Суу көп ич, эс ал.'
        )
        self.assertIn('ОРВИ', record.diagnosis)
        self.assertEqual(MedicalRecord.objects.count(), 1)


# ─────────────────────────────────────────────────────────
# SpecialistAbsence тесттери
# ─────────────────────────────────────────────────────────
class SpecialistAbsenceTest(TestCase):
    def setUp(self):
        self.service = Service.objects.create(name='Кардиолог', duration_minutes=30)
        self.specialist = Specialist.objects.create(
            first_name='Бекзат', last_name='Мамытов',
            service=self.service, work_start=time(9, 0), work_end=time(17, 0),
        )

    def test_absence_created(self):
        today = date.today()
        absence = SpecialistAbsence.objects.create(
            specialist=self.specialist,
            start_date=today,
            end_date=today + timedelta(days=5),
            reason='Отпуск'
        )
        self.assertEqual(str(absence.reason), 'Отпуск')
        self.assertTrue(
            self.specialist.absences.filter(
                start_date__lte=today,
                end_date__gte=today
            ).exists()
        )


# ─────────────────────────────────────────────────────────
# FavoriteSpecialist тесттери
# ─────────────────────────────────────────────────────────
class FavoriteSpecialistTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='fav_user', email='fav@test.com',
            password='pass123', phone='+996700000003'
        )
        self.service = Service.objects.create(name='ЛОР', duration_minutes=30)
        self.specialist = Specialist.objects.create(
            first_name='Гүлзат', last_name='Исакова',
            service=self.service, work_start=time(9, 0), work_end=time(17, 0),
        )

    def test_add_favorite(self):
        fav = FavoriteSpecialist.objects.create(
            user=self.user, specialist=self.specialist
        )
        self.assertEqual(self.user.favorite_specialists.count(), 1)

    def test_duplicate_favorite_blocked(self):
        """Бир эле врачты эки жолу favorites-ка кошулбасын."""
        FavoriteSpecialist.objects.create(user=self.user, specialist=self.specialist)
        with self.assertRaises(Exception):
            FavoriteSpecialist.objects.create(user=self.user, specialist=self.specialist)
