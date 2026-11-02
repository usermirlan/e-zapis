from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()


class RegistrationTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_register_new_user(self):
        response = self.client.post('/accounts/register/', {
            'username': 'newuser',
            'first_name': 'Новый',
            'last_name': 'Пользователь',
            'email': 'new@test.com',
            'phone': '+77001234567',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        self.assertEqual(User.objects.filter(username='newuser').count(), 1)
        # После регистрации — редирект на verify-email
        new_user = User.objects.get(username='newuser')
        self.assertRedirects(response, f'/accounts/verify-email/{new_user.pk}/')

    def test_register_duplicate_email(self):
        User.objects.create_user(
            username='existing',
            email='dupe@test.com',
            password='pass123',
            phone='+77007654321'
        )
        response = self.client.post('/accounts/register/', {
            'username': 'newuser2',
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'email': 'dupe@test.com',
            'phone': '+77001111111',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        # Должна остаться страница регистрации с ошибкой
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)


class LoginTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='logintest',
            email='login@test.com',
            password='testpass123',
            phone='+77009999999'
        )

    def test_login_success(self):
        response = self.client.post('/accounts/login/', {
            'username': 'logintest',
            'password': 'testpass123',
        })
        self.assertRedirects(response, '/')

    def test_login_wrong_password(self):
        response = self.client.post('/accounts/login/', {
            'username': 'logintest',
            'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, 200)

    def test_profile_requires_login(self):
        response = self.client.get('/accounts/profile/')
        self.assertRedirects(response, '/accounts/login/?next=/accounts/profile/')

    def test_profile_accessible_when_logged_in(self):
        self.client.login(username='logintest', password='testpass123')
        response = self.client.get('/accounts/profile/')
        self.assertEqual(response.status_code, 200)

    def test_profile_edit_get(self):
        self.client.login(username='logintest', password='testpass123')
        response = self.client.get('/accounts/profile/')
        self.assertEqual(response.status_code, 200)

    def test_profile_edit_post(self):
        self.client.login(username='logintest', password='testpass123')
        response = self.client.post('/accounts/profile/', {
            'first_name': 'Обновлён',
            'last_name': 'Профиль',
            'email': 'updated@test.com',
            'phone': '+77008888888',
        })
        self.assertRedirects(response, '/accounts/profile/')
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Обновлён')
        self.assertEqual(self.user.email, 'updated@test.com')


class EmailVerificationLimitsTest(TestCase):
    """Защита подтверждения email: лимит неверных попыток и частоты повторной отправки."""

    def setUp(self):
        from django.core.cache import cache
        from .models import EmailVerificationCode
        cache.clear()
        self.user = User.objects.create_user(
            username='unverified', email='u@test.com', password='SecurePass123!',
            phone='+77000000001', is_active=False)
        self.code = EmailVerificationCode.objects.create(user=self.user, code='123456')
        self.url = f'/accounts/verify-email/{self.user.pk}/'

    def test_code_invalidated_after_max_attempts(self):
        from .models import EmailVerificationCode
        for _ in range(EmailVerificationCode.MAX_ATTEMPTS):
            self.client.post(self.url, {'code': '000000'})
        self.assertFalse(EmailVerificationCode.objects.filter(user=self.user).exists())
        # Даже правильный код после этого не активирует аккаунт
        self.client.post(self.url, {'code': '123456'})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_correct_code_activates_after_few_mistakes(self):
        self.client.post(self.url, {'code': '000000'})
        self.client.post(self.url, {'code': '123456'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_resend_throttled_within_a_minute(self):
        self.client.get(f'/accounts/resend-code/{self.user.pk}/')
        self.code.refresh_from_db()
        self.assertEqual(self.code.code, '123456')  # код не перевыпущен
