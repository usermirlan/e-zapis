from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Notification


@receiver(post_save, sender=Notification)
def broadcast_notification(sender, instance, created, **kwargs):
    """Отправка уведомления Real-time через WebSocket при создании записи в БД."""
    if created:
        channel_layer = get_channel_layer()
        if channel_layer:
            group_name = f'user_notifications_{instance.user.id}'
            
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'notification_message',
                    'id': instance.id,
                    'notification_type': instance.notification_type,
                    'notification_type_display': instance.get_notification_type_display(),
                    'message': instance.message,
                    'created_at': instance.created_at.strftime('%H:%M'),
                    'is_read': instance.is_read,
                }
            )
