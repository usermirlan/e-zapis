from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from . import views
from .api_views import ServiceViewSet, SpecialistViewSet, AppointmentViewSet

router = DefaultRouter()
router.register(r'services', ServiceViewSet, basename='api_services_v1')
router.register(r'specialists', SpecialistViewSet, basename='api_specialists_v1')
router.register(r'appointments', AppointmentViewSet, basename='api_appointments_v1')

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
    path('favorites/', views.favorites_view, name='favorites'),
    path('my-appointments/cancel/<int:appointment_id>/', views.cancel_appointment_view, name='cancel_appointment'),
    path('notifications/', views.patient_notifications_view, name='patient_notifications'),
    path('notifications/read-all/', views.patient_mark_all_read_view, name='patient_mark_all_read'),
    path('appointments/<int:appointment_id>/review/', views.add_review_view, name='add_review'),
    path('appointments/<int:appointment_id>/certificate/', views.certificate_view, name='certificate'),

    # ─── Панель сотрудника ─────────────────────────────────────────────────────
    path('staff/', views.staff_panel_view, name='staff_panel'),
    path('staff/doctor/add/', views.staff_add_doctor_view, name='staff_add_doctor'),

    path('staff/appointments/<int:appointment_id>/status/', views.update_appointment_status_view, name='update_appointment_status'),


    # ─── API-эндпоинты (старые, для шаблонов) ──────────────────────────────────
    path('api/services/', views.api_services, name='api_services'),
    path('api/specialists/', views.api_specialists, name='api_specialists'),
    path('api/specialists/<int:specialist_id>/slots/', views.api_time_slots, name='api_time_slots'),
    path('api/favorites/toggle/', views.api_toggle_favorite, name='api_toggle_favorite'),

    # ─── API v1 (Для Мобильного приложения) ────────────────────────────────────
    path('api/v1/', include(router.urls)),
    path('api/v1/auth/login/', obtain_auth_token, name='api_token_auth'),


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

    # ─── Admin Panel ───────────────────────────────────────────────────────────
    path('dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('dashboard/appointments/', views.admin_appointments_view, name='admin_appointments'),
    path('dashboard/appointments/<int:appointment_id>/delete/', views.admin_delete_appointment_view, name='admin_delete_appointment'),
    path('dashboard/specialists/', views.admin_specialists_view, name='admin_specialists'),
    path('dashboard/specialists/add/', views.staff_add_doctor_view, name='admin_add_specialist'),
    path('dashboard/specialists/<int:specialist_id>/absence/', views.admin_specialist_absence_view, name='admin_specialist_absence'),
    path('dashboard/absences/<int:absence_id>/delete/', views.admin_delete_absence_view, name='admin_delete_absence'),
    path('dashboard/specialists/<int:specialist_id>/edit/', views.admin_edit_specialist_view, name='admin_edit_specialist'),
    path('dashboard/specialists/<int:specialist_id>/delete/', views.admin_delete_specialist_view, name='admin_delete_specialist'),
    path('dashboard/specialists/<int:specialist_id>/toggle/', views.admin_toggle_specialist_view, name='admin_toggle_specialist'),
    path('dashboard/services/', views.admin_services_view, name='admin_services'),
    path('dashboard/services/add/', views.admin_add_service_view, name='admin_add_service'),
    path('dashboard/services/<int:service_id>/edit/', views.admin_edit_service_view, name='admin_edit_service'),
    path('dashboard/services/<int:service_id>/delete/', views.admin_delete_service_view, name='admin_delete_service'),
    path('dashboard/services/<int:service_id>/toggle/', views.admin_toggle_service_view, name='admin_toggle_service'),
    path('dashboard/users/', views.admin_users_view, name='admin_users'),
    path('dashboard/users/add/', views.admin_add_user_view, name='admin_add_user'),
    path('dashboard/users/<int:user_id>/role/', views.admin_toggle_user_role_view, name='admin_toggle_user_role'),
    path('dashboard/users/<int:user_id>/toggle/', views.admin_toggle_user_view, name='admin_toggle_user'),
    path('dashboard/users/<int:user_id>/delete/', views.admin_delete_user_view, name='admin_delete_user'),
    path('dashboard/users/<int:user_id>/password/', views.admin_user_change_password_view, name='admin_user_change_password'),
    path('dashboard/users/<int:user_id>/detail/', views.admin_user_detail_view, name='admin_user_detail'),
    path('dashboard/reviews/', views.admin_reviews_view, name='admin_reviews'),
    path('dashboard/reviews/<int:review_id>/delete/', views.admin_delete_review_view, name='admin_delete_review'),

    # ─── Слоты, Мед. карты, Уведомления ─────────────────────────────────────────
    path('dashboard/slots/', views.admin_slots_view, name='admin_slots'),
    path('dashboard/slots/add/', views.admin_add_slot_view, name='admin_add_slot'),
    path('dashboard/slots/bulk/', views.admin_bulk_slots_view, name='admin_bulk_slots'),
    path('dashboard/slots/<int:slot_id>/toggle/', views.admin_toggle_slot_view, name='admin_toggle_slot'),
    path('dashboard/slots/<int:slot_id>/delete/', views.admin_delete_slot_view, name='admin_delete_slot'),
    
    path('dashboard/medical-records/', views.admin_medical_records_view, name='admin_medical_records'),
    path('dashboard/medical-records/<int:record_id>/delete/', views.admin_delete_medical_record_view, name='admin_delete_medical_record'),
    
    path('dashboard/notifications/', views.admin_notifications_view, name='admin_notifications'),
    path('dashboard/notifications/<int:notif_id>/delete/', views.admin_delete_notification_view, name='admin_delete_notification'),
    path('dashboard/notifications/read-all/', views.admin_mark_all_notifications_read_view, name='admin_mark_all_notifications_read'),

    # ─── Инструменты и Экспорт ──────────────────────────────────────────────────
    path('dashboard/settings/', views.admin_settings_view, name='admin_settings'),
    path('dashboard/generate-slots/', views.admin_generate_slots_view, name='admin_generate_slots'),
    path('dashboard/appointments/export/', views.admin_export_appointments_csv, name='admin_export_appointments_csv'),
    path('dashboard/users/export/', views.admin_export_users_csv, name='admin_export_users_csv'),
    path('dashboard/calendar/', views.admin_calendar_view, name='admin_calendar'),
    path('dashboard/api/global-search/', views.admin_global_search_api, name='admin_global_search_api'),

    # ─── Промокоддор, Кезек күтүү, Кара тизме, Аудит, WhatsApp ──────────────────
    path('dashboard/promocodes/', views.admin_promocodes_view, name='admin_promocodes'),
    path('dashboard/promocodes/add/', views.admin_add_promocode_view, name='admin_add_promocode'),
    path('dashboard/promocodes/<int:promo_id>/toggle/', views.admin_toggle_promocode_view, name='admin_toggle_promocode'),
    path('dashboard/promocodes/<int:promo_id>/delete/', views.admin_delete_promocode_view, name='admin_delete_promocode'),

    path('dashboard/waiting-list/', views.admin_waiting_list_view, name='admin_waiting_list'),
    path('dashboard/waiting-list/<int:waiting_id>/status/', views.admin_update_waiting_status_view, name='admin_update_waiting_status'),
    path('dashboard/waiting-list/<int:waiting_id>/delete/', views.admin_delete_waiting_view, name='admin_delete_waiting'),

    path('dashboard/blacklist/', views.admin_blacklist_view, name='admin_blacklist'),
    path('dashboard/blacklist/add/', views.admin_add_penalty_view, name='admin_add_penalty'),
    path('dashboard/blacklist/<int:penalty_id>/toggle/', views.admin_toggle_block_patient_view, name='admin_toggle_block_patient'),
    path('dashboard/blacklist/<int:penalty_id>/reset/', views.admin_reset_missed_count_view, name='admin_reset_missed_count'),

    path('dashboard/audit-logs/', views.admin_audit_logs_view, name='admin_audit_logs'),

    path('dashboard/whatsapp-templates/', views.admin_whatsapp_templates_view, name='admin_whatsapp_templates'),
    path('dashboard/whatsapp-templates/add/', views.admin_add_whatsapp_template_view, name='admin_add_whatsapp_template'),
    path('dashboard/whatsapp-templates/<int:template_id>/toggle/', views.admin_toggle_whatsapp_template_view, name='admin_toggle_whatsapp_template'),
    path('dashboard/whatsapp-templates/<int:template_id>/delete/', views.admin_delete_whatsapp_template_view, name='admin_delete_whatsapp_template'),

    # ─── Медициналык файлдар жана анализдер ─────────────────────────────────────
    path('dashboard/attachments/', views.admin_medical_attachments_view, name='admin_medical_attachments'),
    path('dashboard/attachments/upload/', views.admin_upload_attachment_view, name='admin_upload_attachment'),
    path('dashboard/attachments/<int:attachment_id>/delete/', views.admin_delete_attachment_view, name='admin_delete_attachment'),
]
