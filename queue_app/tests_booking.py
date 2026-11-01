"""
Тесты бизнес-логики записи: защита от овербукинга, повторная запись на
освобождённый слот, суточная нумерация очереди, чёрный список (No-Show),
журнал аудита, REST API v1 и ограничение частоты входа (rate limiting).
"""
import threading
import unittest
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, Client
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import (
    Appointment, AuditLog, PatientPenalty, Service, Specialist, TimeSlot,
)
from .services import (
    BLOCK_DAYS, NO_SHOW_LIMIT, BookingError, book_slot, cancel_appointment,
    get_active_block, register_no_show,
)

User = get_user_model()
TOMORROW = date.today() + timedelta(days=1)


def make_user(n, **extra):
    return User.objects.create_user(
        username=f'patient{n}', email=f'patient{n}@test.kg',
        password='testpass123', phone=f'+99670000{n:04d}', **extra)


class BaseBookingData:
    def make_data(self):
        self.service = Service.objects.create(name='Терапевт', duration_minutes=30)
        self.specialist = Specialist.objects.create(
            first_name='Айбек', last_name='Токтогулов', service=self.service,
            work_start=time(9, 0), work_end=time(17, 0))
        self.slot = TimeSlot.objects.create(
            specialist=self.specialist, date=TOMORROW, time=time(9, 0))
        self.slot2 = TimeSlot.objects.create(
            specialist=self.specialist, date=TOMORROW, time=time(9, 30))
        self.p1 = make_user(1)
        self.p2 = make_user(2)
        self.p3 = make_user(3)


class BookingServiceTest(BaseBookingData, TestCase):
    def setUp(self):
        self.make_data()

    def test_booking_closes_slot_and_assigns_number(self):
        appt = book_slot(self.p1, self.slot.pk, 'Температура')
        self.slot.refresh_from_db()
        self.assertFalse(self.slot.is_available)
        self.assertEqual(appt.queue_number, 1)
        self.assertEqual(appt.status, 'pending')

    def test_second_booking_of_same_slot_rejected(self):
        book_slot(self.p1, self.slot.pk)
        with self.assertRaises(BookingError) as ctx:
            book_slot(self.p2, self.slot.pk)
        self.assertEqual(ctx.exception.code, 'taken')
        self.assertEqual(Appointment.objects.count(), 1)

    def test_rebooking_after_cancellation(self):
        """Регрессия: раньше повторная запись на освобождённый слот давала IntegrityError (HTTP 500)."""
        appt = book_slot(self.p1, self.slot.pk)
        self.assertTrue(cancel_appointment(appt))
        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_available)

        new_appt = book_slot(self.p2, self.slot.pk)
        self.assertEqual(new_appt.patient, self.p2)
        self.assertTrue(AuditLog.objects.filter(action='ARCHIVE_CANCELLED').exists())

    def test_queue_numbers_stay_unique_after_rebooking(self):
        a1 = book_slot(self.p1, self.slot.pk)    # №1
        a2 = book_slot(self.p2, self.slot2.pk)   # №2
        cancel_appointment(a1)
        a3 = book_slot(self.p3, self.slot.pk)    # должен получить №3, а не повтор №2
        self.assertEqual(sorted([a2.queue_number, a3.queue_number]), [2, 3])

    def test_same_patient_cannot_book_twice_a_day(self):
        book_slot(self.p1, self.slot.pk)
        with self.assertRaises(BookingError) as ctx:
            book_slot(self.p1, self.slot2.pk)
        self.assertEqual(ctx.exception.code, 'duplicate')

    def test_past_slot_rejected(self):
        old = TimeSlot.objects.create(specialist=self.specialist,
                                      date=date.today() - timedelta(days=1), time=time(10, 0))
        with self.assertRaises(BookingError) as ctx:
            book_slot(self.p1, old.pk)
        self.assertEqual(ctx.exception.code, 'past')


class NoShowBlacklistTest(BaseBookingData, TestCase):
    def setUp(self):
        self.make_data()

    def _no_show(self, n):
        slot = TimeSlot.objects.create(specialist=self.specialist,
                                       date=TOMORROW + timedelta(days=n), time=time(11, 0))
        appt = book_slot(self.p1, slot.pk)
        return register_no_show(appt)

    def test_three_no_shows_block_patient(self):
        for i in range(NO_SHOW_LIMIT - 1):
            penalty = self._no_show(i)
            self.assertFalse(penalty.is_blocked)
        penalty = self._no_show(NO_SHOW_LIMIT)
        self.assertTrue(penalty.is_blocked)
        self.assertEqual(penalty.missed_count, NO_SHOW_LIMIT)
        days_left = (penalty.blocked_until - timezone.now()).days
        self.assertIn(days_left, (BLOCK_DAYS - 1, BLOCK_DAYS))
        self.assertEqual(AuditLog.objects.filter(action='NO_SHOW').count(), NO_SHOW_LIMIT)

    def test_blocked_patient_cannot_book(self):
        PatientPenalty.objects.create(patient=self.p1, missed_count=3, is_blocked=True,
                                      blocked_until=timezone.now() + timedelta(days=5))
        with self.assertRaises(BookingError) as ctx:
            book_slot(self.p1, self.slot.pk)
        self.assertEqual(ctx.exception.code, 'blocked')

    def test_blocked_patient_redirected_in_web_ui(self):
        PatientPenalty.objects.create(patient=self.p1, missed_count=3, is_blocked=True)
        c = Client()
        c.login(username='patient1', password='testpass123')
        c.post(f'/booking/{self.slot.pk}/', {'complaint': ''})
        self.assertEqual(Appointment.objects.count(), 0)

    def test_expired_block_is_lifted(self):
        PatientPenalty.objects.create(patient=self.p1, missed_count=3, is_blocked=True,
                                      blocked_until=timezone.now() - timedelta(minutes=1))
        self.assertIsNone(get_active_block(self.p1))
        book_slot(self.p1, self.slot.pk)

    def test_doctor_marks_no_show_via_ui(self):
        doctor_user = make_user(9, is_doctor=True)
        self.specialist.user = doctor_user
        self.specialist.save()
        appt = book_slot(self.p1, self.slot.pk)
        c = Client()
        c.login(username='patient9', password='testpass123')
        c.post(f'/doctor/appointments/{appt.pk}/status/', {'status': 'no_show'})
        appt.refresh_from_db()
        self.assertEqual(appt.status, 'no_show')
        self.assertEqual(PatientPenalty.objects.get(patient=self.p1).missed_count, 1)

    def test_status_flow_arrived_in_progress(self):
        doctor_user = make_user(9, is_doctor=True)
        self.specialist.user = doctor_user
        self.specialist.save()
        appt = book_slot(self.p1, self.slot.pk)
        c = Client()
        c.login(username='patient9', password='testpass123')
        for st in ('confirmed', 'arrived', 'in_progress'):
            c.post(f'/doctor/appointments/{appt.pk}/status/', {'status': st})
            appt.refresh_from_db()
            self.assertEqual(appt.status, st)
        self.assertEqual(AuditLog.objects.filter(action='CHANGE_STATUS').count(), 3)


class AdminAuditTest(BaseBookingData, TestCase):
    def setUp(self):
        self.make_data()

    def test_admin_delete_is_logged_with_ip(self):
        admin = User.objects.create_superuser(username='admin', email='admin@test.kg',
                                              password='adminpass123')
        appt = book_slot(self.p1, self.slot.pk)
        c = Client(REMOTE_ADDR='10.0.0.7')
        c.force_login(admin)
        c.post(f'/dashboard/appointments/{appt.pk}/delete/')
        log = AuditLog.objects.get(action='DELETE_APPOINTMENT')
        self.assertEqual(log.user, admin)
        self.assertEqual(log.ip_address, '10.0.0.7')


class RestApiTest(BaseBookingData, TestCase):
    def setUp(self):
        self.make_data()
        self.api = APIClient()
        self.token = Token.objects.create(user=self.p1)

    def _auth(self, user=None):
        token = self.token if user is None else Token.objects.create(user=user)
        self.api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_appointments_require_token(self):
        self.assertEqual(self.api.get('/api/v1/appointments/').status_code, 401)

    def test_create_and_conflict(self):
        self._auth()
        payload = {'specialist_id': self.specialist.pk, 'service_id': self.service.pk,
                   'time_slot_id': self.slot.pk, 'complaint': 'Кашель'}
        r = self.api.post('/api/v1/appointments/', payload, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['queue_number'], 1)

        self._auth(self.p2)
        r2 = self.api.post('/api/v1/appointments/', payload, format='json')
        self.assertEqual(r2.status_code, 409)

    def test_delete_cancels_and_frees_slot(self):
        appt = book_slot(self.p1, self.slot.pk)
        self._auth()
        r = self.api.delete(f'/api/v1/appointments/{appt.pk}/')
        self.assertEqual(r.status_code, 204)
        appt.refresh_from_db()
        self.slot.refresh_from_db()
        self.assertEqual(appt.status, 'cancelled')
        self.assertTrue(self.slot.is_available)

    def test_free_slots_endpoint(self):
        book_slot(self.p1, self.slot.pk)
        r = self.api.get(f'/api/v1/specialists/{self.specialist.pk}/slots/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual([s['id'] for s in r.data], [self.slot2.pk])

    def test_patient_sees_only_own_appointments(self):
        book_slot(self.p1, self.slot.pk)
        book_slot(self.p2, self.slot2.pk)
        self._auth()
        r = self.api.get('/api/v1/appointments/')
        self.assertEqual(r.status_code, 200)
        results = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual(len(results), 1)


class LoginRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        make_user(1)

    def tearDown(self):
        cache.clear()

    def test_sixth_attempt_per_minute_is_limited(self):
        c = Client()
        for _ in range(5):
            r = c.post('/accounts/login/', {'username': 'patient1', 'password': 'wrong'})
            self.assertNotEqual(r.status_code, 429)
        r = c.post('/accounts/login/', {'username': 'patient1', 'password': 'testpass123'})
        self.assertContains(r, 'Слишком много попыток', status_code=429)
        self.assertFalse('_auth_user_id' in c.session)

    def test_open_redirect_blocked(self):
        c = Client()
        r = c.post('/accounts/login/?next=https://evil.example.com/',
                   {'username': 'patient1', 'password': 'testpass123'})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('evil.example.com', r['Location'])


@unittest.skipUnless(connection.vendor == 'postgresql',
                     'Нагрузочный тест гонки требует PostgreSQL (SELECT FOR UPDATE)')
class ConcurrentBookingTest(BaseBookingData, TransactionTestCase):
    """20 параллельных потоков одновременно бронируют один и тот же слот."""
    THREADS = 20

    def setUp(self):
        self.make_data()
        self.patients = [make_user(100 + i) for i in range(self.THREADS)]

    def test_parallel_booking_single_winner(self):
        barrier = threading.Barrier(self.THREADS)
        results = []
        lock = threading.Lock()

        def worker(user):
            try:
                barrier.wait()
                book_slot(user, self.slot.pk)
                outcome = 'ok'
            except BookingError as exc:
                outcome = exc.code
            except Exception as exc:  # любая иная ошибка — провал теста
                outcome = f'error:{exc!r}'
            finally:
                connections.close_all()
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=worker, args=(u,)) for u in self.patients]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count('ok'), 1, results)
        self.assertEqual(results.count('taken'), self.THREADS - 1, results)
        self.assertEqual(Appointment.objects.filter(time_slot=self.slot).count(), 1)

    def test_parallel_booking_different_slots_unique_numbers(self):
        """10 пациентов одновременно бронируют 10 разных слотов одного врача."""
        slots = [TimeSlot.objects.create(specialist=self.specialist, date=TOMORROW,
                                         time=time(12 + i // 2, 30 * (i % 2))) for i in range(10)]
        barrier = threading.Barrier(10)
        errors = []

        def worker(user, slot):
            try:
                barrier.wait()
                book_slot(user, slot.pk)
            except Exception as exc:
                errors.append(repr(exc))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(self.patients[i], slots[i]))
                   for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        numbers = list(Appointment.objects.filter(specialist=self.specialist)
                       .values_list('queue_number', flat=True))
        self.assertEqual(sorted(numbers), list(range(1, 11)))


class AdminActionsSecurityTest(BaseBookingData, TestCase):
    """Изменяющие действия админки принимают только POST и не уводят на чужие сайты."""

    def setUp(self):
        self.make_data()
        self.admin = make_user(9, is_staff=True)
        self.c = Client()
        self.c.force_login(self.admin)

    def test_get_does_not_toggle_user(self):
        r = self.c.get(f'/dashboard/users/{self.p1.pk}/toggle/')
        self.assertEqual(r.status_code, 405)
        self.p1.refresh_from_db()
        self.assertTrue(self.p1.is_active)

    def test_post_toggles_user(self):
        r = self.c.post(f'/dashboard/users/{self.p1.pk}/toggle/')
        self.assertEqual(r.status_code, 302)
        self.p1.refresh_from_db()
        self.assertFalse(self.p1.is_active)

    def test_external_referer_is_ignored(self):
        r = self.c.post(f'/dashboard/slots/{self.slot.pk}/toggle/',
                        HTTP_REFERER='https://evil.example.com/')
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('evil.example.com', r['Location'])
