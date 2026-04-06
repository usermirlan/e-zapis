"""
URL-маршруты приложения accounts.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Регистрация нового пользователя
    path('register/', views.register_view, name='register'),

    # Вход в систему
    path('login/', views.login_view, name='login'),

    # Выход из системы
    path('logout/', views.logout_view, name='logout'),

    # Профиль пользователя
    path('profile/', views.profile_view, name='profile'),
    # Подтверждение email
    path('verify-email/<int:user_id>/', views.verify_email_view, name='verify_email'),
    path('resend-code/<int:user_id>/', views.resend_code_view, name='resend_code'),
]
