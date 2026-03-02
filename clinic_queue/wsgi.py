"""
WSGI config for clinic_queue project.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinic_queue.settings')
application = get_wsgi_application()
