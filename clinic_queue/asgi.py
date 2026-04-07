import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinic_queue.settings')

# Get the basic ASGI application first
application = get_asgi_application()

try:
    # Attempt to wrap it with Channels if available
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.auth import AuthMiddlewareStack
    from queue_app.routing import websocket_urlpatterns
    
    application = ProtocolTypeRouter({
        "http": application,
        "websocket": AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    })
except ImportError:
    # Fallback to standard Django ASGI application if channels is missing
    pass
