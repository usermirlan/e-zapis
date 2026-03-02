

from django.urls import path
from . import views

urlpatterns = [
    # ─── Основные страницы ─────────────────────────────────────────────────────
    path('', views.home_view, name='home'),

    # Список услуг
    path('services/', views.services_view, name='services'),

    # Все специалисты
    path('specialists/', views.specialists_view, name='specialists'),

    # Специалисты по конкретной услуге
    path('specialists/service/<int:service_id>/', views.specialists_view, name='specialists_by_service'),

    # Страница специалиста со слотами
    path('specialists/<int:specialist_id>/', views.specialist_detail_view, name='specialist_detail'),

    # ─── Запись в очередь ──────────────────────────────────────────────────────
    path('booking/<int:slot_id>/', views.booking_view, name='booking'),
    path('booking/success/<int:appointment_id>/', views.appointment_success_view, name='appointment_success'),

    # ─── Личный кабинет ────────────────────────────────────────────────────────
    path('my-appointments/', views.my_appointments_view, name='my_appointments'),
    path('appointments/<int:appointment_id>/cancel/', views.cancel_appointment_view, name='cancel_appointment'),

    # ─── API-эндпоинты (JSON) ──────────────────────────────────────────────────
    path('api/services/', views.api_services, name='api_services'),
    path('api/specialists/', views.api_specialists, name='api_specialists'),
    path('api/specialists/<int:specialist_id>/slots/', views.api_time_slots, name='api_time_slots'),
]
