from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Service, Specialist, TimeSlot, Appointment,
    Notification, Review, MedicalRecord,
    SpecialistAbsence, FavoriteSpecialist, ClinicSetting,
    PromoCode, WaitingList, PatientPenalty, AuditLog, MedicalAttachment, WhatsAppTemplate
)


# ──────────────────────────────────────────────
#  Service
# ──────────────────────────────────────────────
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_minutes', 'is_active', 'is_new', 'specialists_count', 'created_at')
    list_filter = ('is_active', 'is_new')
    search_fields = ('name', 'description')
    list_editable = ('is_active', 'is_new')

    def specialists_count(self, obj):
        count = obj.specialists.filter(is_active=True).count()
        return format_html('<span style="color: #28a745; font-weight: bold;">{}</span>', count)
    specialists_count.short_description = 'Активных специалистов'


# ──────────────────────────────────────────────
#  TimeSlot (inline для Specialist)
# ──────────────────────────────────────────────
class TimeSlotInline(admin.TabularInline):
    model = TimeSlot
    extra = 3
    fields = ('date', 'time', 'is_available')


# ──────────────────────────────────────────────
#  Specialist
# ──────────────────────────────────────────────
@admin.register(Specialist)
class SpecialistAdmin(admin.ModelAdmin):
    list_display = ('get_full_name', 'service', 'experience_years', 'cabinet',
                    'work_start', 'work_end', 'is_active', 'photo_preview')
    list_filter = ('service', 'is_active')
    search_fields = ('last_name', 'first_name', 'middle_name')
    list_editable = ('is_active',)
    inlines = [TimeSlotInline]

    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="width:40px; height:40px; border-radius:50%; object-fit:cover;" />',
                obj.photo.url
            )
        return '—'
    photo_preview.short_description = 'Фото'

    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'ФИО'


# ──────────────────────────────────────────────
#  TimeSlot
# ──────────────────────────────────────────────
@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ('specialist', 'date', 'time', 'is_available')
    list_filter = ('is_available', 'date', 'specialist__service')
    search_fields = ('specialist__last_name', 'specialist__first_name')
    date_hierarchy = 'date'
    list_editable = ('is_available',)


# ──────────────────────────────────────────────
#  Appointment
# ──────────────────────────────────────────────
@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('queue_number', 'patient', 'specialist', 'service',
                    'get_date', 'get_time', 'colored_status', 'created_at')
    list_filter = ('status', 'service', 'specialist', 'time_slot__date')
    search_fields = ('patient__first_name', 'patient__last_name',
                     'specialist__last_name', 'queue_number')
    date_hierarchy = 'created_at'
    readonly_fields = ('queue_number', 'created_at', 'updated_at')

    fieldsets = (
        ('Основная информация', {
            'fields': ('patient', 'service', 'specialist', 'time_slot')
        }),
        ('Статус', {
            'fields': ('status', 'complaint')
        }),
        ('Системная информация', {
            'fields': ('queue_number', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_date(self, obj):
        return obj.time_slot.date
    get_date.short_description = 'Дата'
    get_date.admin_order_field = 'time_slot__date'

    def get_time(self, obj):
        return obj.time_slot.time
    get_time.short_description = 'Время'

    def colored_status(self, obj):
        colors = {
            'pending': '#f0ad4e',
            'confirmed': '#5bc0de',
            'completed': '#5cb85c',
            'cancelled': '#d9534f',
        }
        color = colors.get(obj.status, '#777')
        return format_html(
            '<span style="color:{}; font-weight:bold;">{}</span>',
            color, obj.get_status_display()
        )
    colored_status.short_description = 'Статус'


# ──────────────────────────────────────────────
#  Notification
# ──────────────────────────────────────────────
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'appointment', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'message')
    list_editable = ('is_read',)
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


# ──────────────────────────────────────────────
#  Review
# ──────────────────────────────────────────────
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('patient', 'specialist', 'rating', 'short_comment', 'created_at')
    list_filter = ('rating', 'specialist', 'created_at')
    search_fields = ('patient__first_name', 'patient__last_name',
                     'specialist__last_name', 'comment')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'

    def short_comment(self, obj):
        return obj.comment[:60] + '...' if len(obj.comment) > 60 else obj.comment
    short_comment.short_description = 'Комментарий'


# ──────────────────────────────────────────────
#  MedicalRecord
# ──────────────────────────────────────────────
@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('get_patient', 'get_specialist', 'get_date', 'short_diagnosis', 'created_at')
    search_fields = (
        'appointment__patient__first_name',
        'appointment__patient__last_name',
        'appointment__specialist__last_name',
        'diagnosis',
    )
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'

    def get_patient(self, obj):
        return obj.appointment.patient.get_full_name()
    get_patient.short_description = 'Пациент'

    def get_specialist(self, obj):
        return obj.appointment.specialist.get_full_name()
    get_specialist.short_description = 'Специалист'

    def get_date(self, obj):
        return obj.appointment.time_slot.date
    get_date.short_description = 'Дата приёма'

    def short_diagnosis(self, obj):
        return obj.diagnosis[:60] + '...' if len(obj.diagnosis) > 60 else obj.diagnosis
    short_diagnosis.short_description = 'Диагноз'


# ──────────────────────────────────────────────
#  SpecialistAbsence
# ──────────────────────────────────────────────
@admin.register(SpecialistAbsence)
class SpecialistAbsenceAdmin(admin.ModelAdmin):
    list_display = ('specialist', 'start_date', 'end_date', 'reason', 'created_at')
    list_filter = ('specialist', 'start_date')
    search_fields = ('specialist__last_name', 'specialist__first_name', 'reason')
    date_hierarchy = 'start_date'
    readonly_fields = ('created_at',)


# ──────────────────────────────────────────────
#  FavoriteSpecialist
# ──────────────────────────────────────────────
@admin.register(FavoriteSpecialist)
class FavoriteSpecialistAdmin(admin.ModelAdmin):
    list_display = ('user', 'specialist', 'created_at')
    list_filter = ('specialist__service',)
    search_fields = ('user__first_name', 'user__last_name', 'specialist__last_name')
    readonly_fields = ('created_at',)


# ──────────────────────────────────────────────
#  ClinicSetting
# ──────────────────────────────────────────────
@admin.register(ClinicSetting)
class ClinicSettingAdmin(admin.ModelAdmin):
    list_display = ('clinic_name', 'phone', 'email', 'address', 'work_hours', 'updated_at')
    readonly_fields = ('updated_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('clinic_name', 'phone', 'email', 'address', 'work_hours')
        }),
        ('Социальные сети', {
            'fields': ('whatsapp_number', 'instagram_url', 'telegram_url')
        }),
        ('Системная информация', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        # Только одна запись настроек
        return not ClinicSetting.objects.exists()


# ──────────────────────────────────────────────
#  PromoCode
# ──────────────────────────────────────────────
@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_percent', 'discount_amount', 'valid_from', 'valid_until', 'used_count', 'max_uses', 'is_active')
    list_filter = ('is_active', 'valid_until')
    search_fields = ('code', 'description')
    list_editable = ('is_active',)


# ──────────────────────────────────────────────
#  WaitingList
# ──────────────────────────────────────────────
@admin.register(WaitingList)
class WaitingListAdmin(admin.ModelAdmin):
    list_display = ('patient', 'specialist', 'preferred_date', 'status', 'created_at')
    list_filter = ('status', 'specialist', 'preferred_date')
    search_fields = ('patient__first_name', 'patient__last_name', 'specialist__last_name', 'notes')
    list_editable = ('status',)
    date_hierarchy = 'preferred_date'


# ──────────────────────────────────────────────
#  PatientPenalty (Blacklist)
# ──────────────────────────────────────────────
@admin.register(PatientPenalty)
class PatientPenaltyAdmin(admin.ModelAdmin):
    list_display = ('patient', 'missed_count', 'is_blocked', 'blocked_until', 'reason', 'updated_at')
    list_filter = ('is_blocked',)
    search_fields = ('patient__first_name', 'patient__last_name', 'patient__phone', 'reason')
    list_editable = ('is_blocked', 'missed_count')


# ──────────────────────────────────────────────
#  AuditLog
# ──────────────────────────────────────────────
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'short_details', 'ip_address')
    list_filter = ('action', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'action', 'details', 'ip_address')
    readonly_fields = ('user', 'action', 'details', 'ip_address', 'created_at')
    date_hierarchy = 'created_at'

    def short_details(self, obj):
        return obj.details[:70] + '...' if len(obj.details) > 70 else obj.details
    short_details.short_description = 'Детали'

    def has_add_permission(self, request):
        return False


# ──────────────────────────────────────────────
#  MedicalAttachment
# ──────────────────────────────────────────────
@admin.register(MedicalAttachment)
class MedicalAttachmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'patient', 'file_type', 'appointment', 'created_at')
    list_filter = ('file_type', 'created_at')
    search_fields = ('title', 'patient__first_name', 'patient__last_name', 'comment')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


# ──────────────────────────────────────────────
#  WhatsAppTemplate
# ──────────────────────────────────────────────
@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    list_display = ('title', 'template_type', 'is_active', 'updated_at')
    list_filter = ('template_type', 'is_active')
    search_fields = ('title', 'message')
    list_editable = ('is_active',)
