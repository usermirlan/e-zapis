import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinic_queue.settings')
django.setup()

from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site

print("--- SOCIAL APPS IN DB ---")
for app in SocialApp.objects.all():
    print(f"ID: {app.id}")
    print(f"Provider: {app.provider}")
    print(f"Name: {app.name}")
    print(f"Client ID: {app.client_id}")
    print(f"Sites: {[site.domain for site in app.sites.all()]}")
    print("-" * 20)

print("\n--- SITES ---")
for site in Site.objects.all():
    print(f"ID: {site.id}, Domain: {site.domain}, Name: {site.name}")
