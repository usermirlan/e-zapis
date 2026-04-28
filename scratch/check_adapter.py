import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinic_queue.settings')
django.setup()

from accounts.adapter import RobustSocialAccountAdapter
from django.http import HttpRequest

adapter = RobustSocialAccountAdapter()
request = HttpRequest()
app = adapter.get_app(request, 'google')

print(f"--- ADAPTER OUTPUT ---")
print(f"Provider: {app.provider}")
print(f"Client ID: {app.client_id}")
print(f"Secret: {app.secret}")

if app.client_id == '64890493821-0l7u8i3m36lk3l9n0bujdivvj7igll.apps.googleusercontent.com':
    print("\nSUCCESS: Client ID matches the correct version (starting with 0l7u).")
else:
    print(f"\nFAILURE: Client ID is still incorrect: {app.client_id}")
