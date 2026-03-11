from .models import Notification

def notification_processor(request):
    """Добавляет количество непрочитанных уведомлений в контекст всех шаблонов."""
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        return {'unread_notifications_count': unread_count}
    return {'unread_notifications_count': 0}
