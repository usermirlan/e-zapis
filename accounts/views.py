from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from .forms import RegisterForm, LoginForm, ProfileEditForm
from .models import CustomUser, EmailVerificationCode
import logging

logger = logging.getLogger(__name__)

# Rate limiting (django-ratelimit) — graceful fallback
try:
    from ratelimit.decorators import ratelimit
    _RATELIMIT_AVAILABLE = True
except ImportError:
    _RATELIMIT_AVAILABLE = False
    def ratelimit(*args, **kwargs):
        """No-op decorator if django-ratelimit is not installed."""
        def decorator(func): return func
        return decorator



@ratelimit(key='ip', rate='3/m', method='POST', block=False)
def register_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.is_staff:
            return redirect('admin_dashboard')
        return redirect('home')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Деактивируем пользователя до подтверждения email
            user.is_active = False
            user.save()

            # Генерируем и сохраняем код
            code_str = EmailVerificationCode.generate_code()
            EmailVerificationCode.objects.update_or_create(
                user=user,
                defaults={'code': code_str}
            )

            # Отправляем письмо
            try:
                subject = 'Подтверждение регистрации — МедЗапись'
                message = f'Здравствуйте, {user.get_full_name()}!\n\nВаш код для подтверждения регистрации: {code_str}\n\nВведите его на странице подтверждения, чтобы активировать аккаунт.'
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
                messages.success(request, 'Код подтверждения отправлен на ваш email.')
            except Exception as e:
                print(f"Error sending email: {e}")
                messages.warning(request, 'Не удалось отправить email, но аккаунт создан. Пожалуйста, обратитесь в поддержку или попробуйте позже.')

            return redirect('verify_email', user_id=user.id)
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def verify_email_view(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    
    if user.is_active:
        messages.info(request, 'Ваш email уже подтвержден.')
        return redirect('login')

    if request.method == 'POST':
        code_input = request.POST.get('code')
        try:
            verification = EmailVerificationCode.objects.get(user=user)
            if verification.code == code_input:
                if verification.is_expired():
                    messages.error(request, 'Код истек. Пожалуйста, запросите новый код.')
                else:
                    # Успех!
                    user.is_active = True
                    user.save()
                    verification.delete()
                    
                    # Автоматический вход
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    messages.success(request, f'Добро пожаловать, {user.get_full_name()}! Ваш email успешно подтвержден.')
                    return redirect('home')
            else:
                messages.error(request, 'Неверный код. Пожалуйста, проверьте и попробуйте снова.')
        except EmailVerificationCode.DoesNotExist:
            messages.error(request, 'Код не найден. Пожалуйста, запросите новый код.')

    return render(request, 'accounts/verify_email.html', {'target_user': user})


def resend_code_view(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    
    if user.is_active:
        return redirect('login')

    # Генерируем новый код
    code_str = EmailVerificationCode.generate_code()
    
    # Удаляем старый код и создаем новый, чтобы обновить время создания (timestamp)
    EmailVerificationCode.objects.filter(user=user).delete()
    EmailVerificationCode.objects.create(user=user, code=code_str)

    try:
        subject = 'Новый код подтверждения — МедЗапись'
        message = f'Ваш новый код для подтверждения регистрации: {code_str}'
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        messages.success(request, 'Новый код успешно отправлен на вашу почту.')
    except Exception:
        messages.error(request, 'Ошибка при отправке почты.')

    return redirect('verify_email', user_id=user.id)



@ratelimit(key='ip', rate='5/m', method='POST', block=False)
def login_view(request):
    # Rate limit exceeded?  
    was_limited = getattr(request, 'limited', False)
    if was_limited:
        messages.error(request, 'Өтүнмө: Өтө көп аракет. 1 мүнөттөн кийин кайра аракет кылыңыз.')
        return render(request, 'accounts/login.html', {'form': LoginForm()})

    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.is_staff:
            return redirect('admin_dashboard')
        if request.user.is_doctor:
            return redirect('doctor_dashboard')
        return redirect('home')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.get_full_name()}!')
            # Если администратор — перенаправить в админ-панель
            if user.is_superuser or user.is_staff:
                return redirect('admin_dashboard')
            # Если врач — перенаправить в кабинет врача
            if user.is_doctor:
                return redirect('doctor_dashboard')
            next_url = request.GET.get('next', 'home')
            if next_url == 'home' and (user.is_superuser or user.is_staff):
                return redirect('admin_dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Неверный логин или пароль.')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'Вы успешно вышли из системы.')
    return redirect('login')


@login_required
def profile_view(request):
    if request.user.is_doctor:
        return redirect('doctor_dashboard')
        
    """Единый профиль пользователя (с радактированием)."""
    appointments = request.user.appointments.select_related(
        'specialist', 'service', 'time_slot'
    ).order_by('-created_at')

    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль успешно обновлён!')
            return redirect('profile')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = ProfileEditForm(instance=request.user)

    return render(request, 'accounts/profile.html', {
        'user': request.user,
        'appointments': appointments,
        'form': form,
    })

class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('profile')

    def form_valid(self, form):
        messages.success(self.request, 'Ваш пароль успешно изменен!')
        return super().form_valid(form)
