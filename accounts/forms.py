from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import CustomUser


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=50,
        label='Имя',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите имя'
        })
    )
    last_name = forms.CharField(
        max_length=50,
        label='Фамилия',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите фамилию'
        })
    )
    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@mail.com'
        })
    )
    phone = forms.CharField(
        max_length=20,
        label='Номер телефона',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+996 XXX XXXXXX'
        })
    )
    date_of_birth = forms.DateField(
        required=False,
        label='Дата рождения',
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Минимум 8 символов'
        })
    )
    password2 = forms.CharField(
        label='Подтвердите пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Повторите пароль'
        })
    )

    class Meta:
        model = CustomUser
        fields = ('username', 'first_name', 'last_name', 'email', 'phone',
                  'date_of_birth', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Логин (латинские буквы)'
            }),
        }
        labels = {
            'username': 'Логин',
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже существует.')
        return email


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Логин',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ваш логин'
        })
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ваш пароль'
        })
    )


class ProfileEditForm(forms.ModelForm):
    """Форма редактирования профиля пользователя."""

    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'phone', 'date_of_birth', 'photo')
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите имя'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите фамилию'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'example@mail.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+996 XXX XXXXXX'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'photo': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
        labels = {
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'email': 'Email',
            'phone': 'Номер телефона',
            'date_of_birth': 'Дата рождения',
            'photo': 'Фотография профиля',
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        qs = CustomUser.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Пользователь с таким email уже существует.')
        return email


class DoctorRegisterForm(UserCreationForm):
    """Форма регистрации врача — создаёт CustomUser + Specialist."""

    first_name = forms.CharField(
        max_length=50,
        label='Имя',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите имя'
        })
    )
    last_name = forms.CharField(
        max_length=50,
        label='Фамилия',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите фамилию'
        })
    )
    middle_name = forms.CharField(
        max_length=50,
        required=False,
        label='Отчество',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите отчество (необязательно)'
        })
    )
    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@mail.com'
        })
    )
    phone = forms.CharField(
        max_length=20,
        label='Номер телефона',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+996 XXX XXXXXX'
        })
    )
    service = forms.ModelChoiceField(
        queryset=None,
        label='Специализация',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    experience_years = forms.IntegerField(
        label='Стаж (лет)',
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Опыт работы в годах'
        })
    )
    cabinet = forms.CharField(
        max_length=20,
        required=False,
        label='Номер кабинета',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Например: 205'
        })
    )
    work_start = forms.TimeField(
        label='Начало рабочего дня',
        widget=forms.TimeInput(attrs={
            'class': 'form-control',
            'type': 'time',
            'value': '09:00'
        })
    )
    work_end = forms.TimeField(
        label='Конец рабочего дня',
        widget=forms.TimeInput(attrs={
            'class': 'form-control',
            'type': 'time',
            'value': '18:00'
        })
    )
    bio = forms.CharField(
        label='О себе / Биография',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Расскажите о вашем образовании, опыте и подходе к лечению...'
        })
    )
    photo = forms.ImageField(
        label='Фотография профиля',
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        })
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Минимум 8 символов'
        })
    )
    password2 = forms.CharField(
        label='Подтвердите пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Повторите пароль'
        })
    )

    class Meta:
        model = CustomUser
        fields = ('username', 'first_name', 'last_name', 'email', 'phone',
                  'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Логин (латинские буквы)'
            }),
        }
        labels = {
            'username': 'Логин',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from queue_app.models import Service
        self.fields['service'].queryset = Service.objects.filter(is_active=True)

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже существует.')
        return email

    def save(self, commit=True):
        from queue_app.models import Specialist, TimeSlot
        from datetime import date, datetime, timedelta
        
        user = super().save(commit=False)
        user.is_doctor = True
        if commit:
            user.save()
            specialist = Specialist.objects.create(
                user=user,
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                middle_name=self.cleaned_data.get('middle_name', ''),
                service=self.cleaned_data['service'],
                experience_years=self.cleaned_data.get('experience_years', 0),
                cabinet=self.cleaned_data.get('cabinet', ''),
                work_start=self.cleaned_data['work_start'],
                work_end=self.cleaned_data['work_end'],
                bio=self.cleaned_data.get('bio', ''),
                photo=self.cleaned_data.get('photo', None)
            )
            
            # Автоматическая генерация слотов (свободное время и число) на 14 дней
            today = date.today()
            duration = specialist.service.duration_minutes
            for i in range(1, 15): 
                current_date = today + timedelta(days=i)
                if current_date.weekday() < 5:  # Только будние дни (Пн-Пт)
                    current_dt = datetime.combine(current_date, specialist.work_start)
                    end_dt = datetime.combine(current_date, specialist.work_end)
                    
                    while current_dt + timedelta(minutes=duration) <= end_dt:
                        # Обед с 13:00 до 14:00 (пропуск слотов)
                        lunch_start = datetime.strptime('13:00', '%H:%M').time()
                        lunch_end = datetime.strptime('14:00', '%H:%M').time()
                        
                        if lunch_start <= current_dt.time() < lunch_end:
                            current_dt += timedelta(minutes=duration)
                            continue
                            
                        TimeSlot.objects.create(
                            specialist=specialist,
                            date=current_date,
                            time=current_dt.time()
                        )
                        current_dt += timedelta(minutes=duration)
        return user
