from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/queue/(?P<specialist_id>\d+)/$', consumers.QueueConsumer.as_asgi()),
]
