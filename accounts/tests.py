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
        self.assertRedirects(response, '/accounts/verify-email/1/')

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
