from django.db import models
from django.conf import settings
from django.utils import timezone


class Service(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название услуги')
    description = models.TextField(blank=True, verbose_name='Описание')
    icon = models.CharField(
        max_length=50,
        default='bi-heart-pulse',
        verbose_name='Bootstrap иконка',
        help_text='Например: bi-heart-pulse, bi-bandaid, bi-clipboard2-pulse'
    )
    # Длительность одного приёма в минутах
    duration_minutes = models.PositiveIntegerField(
        default=30,
        verbose_name='Длительность приёма (мин)'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Услуга'
        verbose_name_plural = 'Услуги'
        ordering = ['name']

    def __str__(self):
        return self.name


class Specialist(models.Model):
    first_name = models.CharField(max_length=50, verbose_name='Имя')
    last_name = models.CharField(max_length=50, verbose_name='Фамилия')
    middle_name = models.CharField(max_length=50, blank=True, verbose_name='Отчество')

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='specialist_profile',
        verbose_name='Аккаунт пользователя'
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='specialists',
        verbose_name='Специализация'
    )

    bio = models.TextField(blank=True, verbose_name='Биография / О враче')
    experience_years = models.PositiveIntegerField(default=0, verbose_name='Стаж (лет)')
    photo = models.ImageField(
        upload_to='specialists/',
        blank=True,
        null=True,
        verbose_name='Фото'
    )
    cabinet = models.CharField(max_length=20, blank=True, verbose_name='Кабинет')

    # Рабочие часы
    work_start = models.TimeField(default='09:00', verbose_name='Начало рабочего дня')
    work_end = models.TimeField(default='18:00', verbose_name='Конец рабочего дня')

    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Специалист'
        verbose_name_plural = 'Специалисты'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f'{self.last_name} {self.first_name} {self.middle_name} — {self.service.name}'

    def get_full_name(self):
        """Полное ФИО специалиста."""
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return ' '.join(parts)

    @property
    def average_rating(self):
        """Средний рейтинг специалиста."""
        reviews = self.reviews.all()
        if not reviews.exists():
            return 0
        return round(sum(r.rating for r in reviews) / reviews.count(), 1)


class TimeSlot(models.Model):

    specialist = models.ForeignKey(
        Specialist,
        on_delete=models.CASCADE,
        related_name='time_slots',
        verbose_name='Специалист'
    )
    date = models.DateField(verbose_name='Дата')
    time = models.TimeField(verbose_name='Время')

    is_available = models.BooleanField(default=True, verbose_name='Доступен')

    class Meta:
        verbose_name = 'Временной слот'
        verbose_name_plural = 'Временные слоты'
        ordering = ['date', 'time']
        unique_together = ('specialist', 'date', 'time')

    def __str__(self):
        status = '✓' if self.is_available else '✗'
        return f'{self.specialist.last_name} | {self.date} {self.time} [{status}]'


class Appointment(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('confirmed', 'Подтверждена'),
        ('completed', 'Завершена'),
        ('cancelled', 'Отменена'),
    ]

    # Пациент (пользователь системы)
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='appointments',
        verbose_name='Пациент'
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='appointments',
        verbose_name='Услуга'
    )
    specialist = models.ForeignKey(
        Specialist,
        on_delete=models.CASCADE,
        related_name='appointments',
        verbose_name='Специалист'
    )

    time_slot = models.OneToOneField(
        TimeSlot,
        on_delete=models.CASCADE,
        related_name='appointment',
        verbose_name='Временной слот'
    )

    queue_number = models.PositiveIntegerField(verbose_name='Номер очереди', editable=False)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )

    complaint = models.TextField(blank=True, verbose_name='Причина обращения')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Запись'
        verbose_name_plural = 'Записи'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
      
        if not self.pk:  # Только при создании новой записи
            today = self.time_slot.date
            existing_count = Appointment.objects.filter(
                specialist=self.specialist,
                time_slot__date=today
            ).count()
            self.queue_number = existing_count + 1

            self.time_slot.is_available = False
            self.time_slot.save()

        super().save(*args, **kwargs)

    def __str__(self):
        return f'Очередь №{self.queue_number} | {self.patient.get_full_name()} → {self.specialist.last_name}'

    def get_status_badge_class(self):
        """Возвращает Bootstrap класс для цвета статуса."""
        badge_map = {
            'pending': 'warning',
            'confirmed': 'primary',
            'completed': 'success',
            'cancelled': 'danger',
        }
        return badge_map.get(self.status, 'secondary')


class Notification(models.Model):
    """Уведомления для врачей о записях пациентов."""

    TYPE_CHOICES = [
        ('new_appointment', 'Новая запись'),
        ('cancelled', 'Отмена записи'),
        ('status_update', 'Обновление статуса'),
        ('reminder', 'Напоминание'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Пользователь'
    )
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name='Запись'
    )
    notification_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='new_appointment',
        verbose_name='Тип'
    )
    message = models.TextField(verbose_name='Сообщение')
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_notification_type_display()} — {self.user.get_full_name()}'


class Review(models.Model):
    """Отзывы пациентов о врачах."""
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='Пациент'
    )
    specialist = models.ForeignKey(
        Specialist,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='Специалист'
    )
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='review',
        verbose_name='Запись',
        null=True,
        blank=True
    )
    rating = models.PositiveSmallIntegerField(
        verbose_name='Рейтинг',
        choices=[(i, i) for i in range(1, 6)],
        default=5
    )
    comment = models.TextField(verbose_name='Комментарий', blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['-created_at']
        unique_together = ('patient', 'appointment')

    def __str__(self):
        return f'Отзыв от {self.patient.get_full_name()} для {self.specialist.last_name}'


class MedicalRecord(models.Model):
    """Медицинская запись по итогам приема."""
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='medical_record',
        verbose_name='Запись на прием'
    )
    diagnosis = models.TextField(verbose_name='Диагноз')
    recommendations = models.TextField(verbose_name='Рекомендации')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'Медицинская запись'
        verbose_name_plural = 'Медицинские записи'
        ordering = ['-created_at']

    def __str__(self):
        return f'Мед. запись для {self.appointment.patient.get_full_name()} ({self.appointment.time_slot.date})'


class SpecialistAbsence(models.Model):
    """Отсутствие специалиста (отпуск, больничный, выходной)."""
    specialist = models.ForeignKey(
        Specialist,
        on_delete=models.CASCADE,
        related_name='absences',
        verbose_name='Специалист'
    )
    start_date = models.DateField(verbose_name='Дата начала')
    end_date = models.DateField(verbose_name='Дата окончания')
    reason = models.CharField(
        max_length=255, 
        blank=True, 
        verbose_name='Причина',
        help_text='Например: Отпуск, Больничный, Личные обстоятельства'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'Отсутствие специалиста'
        verbose_name_plural = 'Отсутствие специалистов'
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.specialist.last_name} | {self.start_date} — {self.end_date}'

