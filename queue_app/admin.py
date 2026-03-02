from django.contrib import admin
from django.utils.html import format_html
from .models import Service, Specialist, TimeSlot, Appointment


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_minutes', 'is_active', 'specialists_count')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    list_editable = ('is_active',)

    def specialists_count(self, obj):
        count = obj.specialists.filter(is_active=True).count()
        return format_html('<span style="color: #28a745; font-weight: bold;">{}</span>', count)
    specialists_count.short_description = 'Активных специалистов'


class TimeSlotInline(admin.TabularInline):
    model = TimeSlot
    extra = 3  
    fields = ('date', 'time', 'is_available')


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


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ('specialist', 'date', 'time', 'is_available')
    list_filter = ('is_available', 'date', 'specialist__service')
    search_fields = ('specialist__last_name', 'specialist__first_name')
    date_hierarchy = 'date'
    list_editable = ('is_available',)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):

    list_display = ('queue_number', 'patient', 'specialist', 'service',
                    'get_date', 'get_time', 'status', 'created_at')
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
