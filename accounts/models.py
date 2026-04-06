from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta
import random


class CustomUser(AbstractUser):
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Номер телефона',
        help_text='Формат: +996 XXX XXXXXX'
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        verbose_name='Дата рождения'
    )
    is_doctor = models.BooleanField(
        default=False,
        verbose_name='Врач',
        help_text='Отметьте, если пользователь является врачом'
    )
    photo = models.ImageField(
        upload_to='users/',
        blank=True,
        null=True,
        verbose_name='Фото профиля'
    )

    email = models.EmailField(unique=True, verbose_name='Email')

    REQUIRED_FIELDS = ['email', 'first_name', 'last_name', 'phone']

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return f'{self.get_full_name()} ({self.username})'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.username


class EmailVerificationCode(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='verification_code')
    code = models.CharField(max_length=6, verbose_name='Код подтверждения')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'Код подтверждения'
        verbose_name_plural = 'Коды подтверждения'

    def __str__(self):
        return f'Код для {self.user.email}: {self.code}'

    def is_expired(self):
        # Код действителен 10 минут
        return timezone.now() > self.created_at + timedelta(minutes=10)

    @staticmethod
    def generate_code():
        return str(random.randint(100000, 999999))
