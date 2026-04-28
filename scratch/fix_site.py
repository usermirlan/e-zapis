import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinic_queue.settings')
django.setup()

from django.contrib.sites.models import Site

site = Site.objects.get(id=1)
site.domain = '127.0.0.1:8000'
site.name = 'MedZapis Local'
site.save()

print(f"Site domain updated to: {site.domain}")
