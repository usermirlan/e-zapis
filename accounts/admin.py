from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, EmailVerificationCode


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'phone', 'is_doctor', 'is_active', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_doctor', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('Дополнительная информация', {
            'fields': ('phone', 'date_of_birth', 'is_doctor', 'photo'),
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Личные данные', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'date_of_birth', 'is_doctor'),
        }),
    )


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'created_at', 'is_expired_display')
    search_fields = ('user__email', 'user__username', 'code')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def is_expired_display(self, obj):
        from django.utils.html import format_html
        expired = obj.is_expired()
        color = '#d9534f' if expired else '#5cb85c'
        label = 'Истёк' if expired else 'Активен'
        return format_html('<span style="color:{}; font-weight:bold;">{}</span>', color, label)
    is_expired_display.short_description = 'Статус кода'
