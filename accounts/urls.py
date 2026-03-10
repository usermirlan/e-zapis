"""
URL-маршруты приложения accounts.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Регистрация нового пользователя
    path('register/', views.register_view, name='register'),

    # Регистрация врача
    path('register/doctor/', views.doctor_register_view, name='doctor_register'),

    # Вход в систему
    path('login/', views.login_view, name='login'),

    # Выход из системы
    path('logout/', views.logout_view, name='logout'),

    # Профиль пользователя
    path('profile/', views.profile_view, name='profile'),
]
