import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinic_queue.settings')
django.setup()

try:
    from allauth.socialaccount.models import SocialApp
    from django.contrib.sites.models import Site
    
    print(f"--- ДИАГНОСТИКА ---")
    print(f"Текущий SITE_ID в настройках: {settings.SITE_ID}")
    
    try:
        current_site = Site.objects.get(id=settings.SITE_ID)
        print(f"Текущий сайт в базе: {current_site.domain} (ID: {current_site.id})")
    except Site.DoesNotExist:
        print(f"ОШИБКА: Сайт с ID {settings.SITE_ID} не найден в базе данных!")

    apps = SocialApp.objects.all()
    print(f"\nВсего найдено SocialApp: {apps.count()}")
    
    for app in apps:
        sites = list(app.sites.all())
        site_ids = [s.id for s in sites]
        print(f"ID: {app.id} | Provider: {app.provider} | Name: {app.name} | Привязан к Site IDs: {site_ids}")
        
    google_apps = SocialApp.objects.filter(provider='google', sites__id=settings.SITE_ID)
    if google_apps.count() > 1:
        print(f"\nКРИТИЧЕСКАЯ ОШИБКА: Найдено {google_apps.count()} приложений Google для SITE_ID {settings.SITE_ID}!")
        print("Удаляю лишние, оставляю только одно...")
        to_keep = google_apps.first()
        for dup in google_apps.exclude(id=to_keep.id):
            dup.sites.remove(current_site)
            # Если у приложения больше нет сайтов, удаляем его совсем
            if dup.sites.count() == 0:
                dup.delete()
        print("Очистка дублей для текущего сайта завершена.")
    else:
        print("\nДля текущего SITE_ID найдено 0 или 1 приложение Google. Проблема в чем-то другом.")

except Exception as e:
    print(f"Ошибка при диагностике: {e}")
