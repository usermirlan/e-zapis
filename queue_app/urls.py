from django.urls import path
from . import views

urlpatterns = [
    # ─── Основные страницы ─────────────────────────────────────────────────────
    path('', views.home_view, name='home'),

    # Список услуг
    path('services/', views.services_view, name='services'),

    # Все специалисты (с поиском: ?q=)
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
    path('my-appointments/cancel/<int:appointment_id>/', views.cancel_appointment_view, name='cancel_appointment'),
    path('notifications/', views.patient_notifications_view, name='patient_notifications'),
    path('notifications/read-all/', views.patient_mark_all_read_view, name='patient_mark_all_read'),
    path('appointments/<int:appointment_id>/review/', views.add_review_view, name='add_review'),

    # ─── Панель сотрудника ─────────────────────────────────────────────────────
    path('staff/', views.staff_panel_view, name='staff_panel'),
    path('staff/doctor/add/', views.staff_add_doctor_view, name='staff_add_doctor'),
    path('staff/appointments/<int:appointment_id>/status/', views.update_appointment_status_view, name='update_appointment_status'),


    # ─── API-эндпоинты (JSON) ──────────────────────────────────────────────────
    path('api/services/', views.api_services, name='api_services'),
    path('api/specialists/', views.api_specialists, name='api_specialists'),
    path('api/specialists/<int:specialist_id>/slots/', views.api_time_slots, name='api_time_slots'),

    # ─── Кабинет врача ────────────────────────────────────────────────────────
    path('doctor/dashboard/', views.doctor_dashboard_view, name='doctor_dashboard'),
    path('doctor/appointments/', views.doctor_appointments_view, name='doctor_appointments'),
    path('doctor/appointments/<int:appointment_id>/status/', views.doctor_update_status_view, name='doctor_update_status'),
    path('doctor/appointments/<int:appointment_id>/medical-record/', views.doctor_add_medical_record_view, name='doctor_add_medical_record'),
    path('doctor/generate-slots/', views.doctor_generate_slots_view, name='doctor_generate_slots'),
    path('doctor/manage-slots/', views.doctor_manage_slots_view, name='doctor_manage_slots'),
    path('doctor/slots/<int:slot_id>/delete/', views.doctor_delete_slot_view, name='doctor_delete_slot'),
    path('doctor/slots/<int:slot_id>/edit/', views.doctor_edit_slot_view, name='doctor_edit_slot'),
    path('doctor/slots/bulk-actions/', views.doctor_bulk_actions_view, name='doctor_bulk_actions'),
    path('doctor/add-manual-slot/', views.doctor_add_manual_slot_view, name='doctor_add_manual_slot'),
    path('doctor/patients/', views.doctor_patients_view, name='doctor_patients'),
    path('doctor/notifications/', views.doctor_notifications_view, name='doctor_notifications'),
    path('doctor/notifications/<int:notification_id>/read/', views.doctor_mark_read_view, name='doctor_mark_read'),
    path('doctor/notifications/read-all/', views.doctor_mark_all_read_view, name='doctor_mark_all_read'),
    path('doctor/profile/', views.doctor_profile_view, name='doctor_profile'),
]
