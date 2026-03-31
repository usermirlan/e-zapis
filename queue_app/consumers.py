import json
from channels.generic.websocket import AsyncWebsocketConsumer


class QueueConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time queue updates.
    Patients connect to ws/queue/<specialist_id>/ and receive
    live updates when their appointment status changes.
    """

    async def connect(self):
        self.specialist_id = self.scope['url_route']['kwargs']['specialist_id']
        self.group_name = f'queue_{self.specialist_id}'

        # Join the specialist's queue group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Leave the group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        # Clients can send a ping to keep connection alive
        data = json.loads(text_data)
        if data.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

    async def queue_update(self, event):
        """
        Called when doctor updates an appointment status.
        Broadcasts the update to all connected patients.
        """
        await self.send(text_data=json.dumps({
            'type': 'queue_update',
            'appointment_id': event['appointment_id'],
            'status': event['status'],
            'status_display': event['status_display'],
            'queue_number': event['queue_number'],
        }))

class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time user-specific notifications.
    Each user (doctor/patient) connects to their unique group to receive events.
    """
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
            return
            
        self.user_id = self.scope["user"].id
        self.group_name = f'user_notifications_{self.user_id}'

        # Join personal user's notification group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def notification_message(self, event):
        """
        Called when a new Notification is saved (via signal).
        Sends the data to the connected user's WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'id': event['id'],
            'notification_type': event['notification_type'],
            'notification_type_display': event['notification_type_display'],
            'message': event['message'],
            'created_at': event['created_at'],
            'is_read': event['is_read'],
        }))
