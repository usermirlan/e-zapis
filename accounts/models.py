from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    phone = models.CharField(
        max_length=20,
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
