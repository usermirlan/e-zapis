import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinic_queue.settings')
django.setup()

try:
    from allauth.socialaccount.models import SocialApp
    
    # Ищем все приложения для google
    google_apps = SocialApp.objects.filter(provider='google')
    
    if google_apps.count() > 1:
        print(f"Найдено {google_apps.count()} дубликатов для Google. Удаляю лишние...")
        # Оставляем только самое первое (или последнее), остальные удаляем
        to_keep = google_apps.first()
        SocialApp.objects.filter(provider='google').exclude(id=to_keep.id).delete()
        print(f"Очистка завершена. Оставлено приложение с ID: {to_keep.id}")
    elif google_apps.count() == 1:
        print("Настройка Google в порядке (всего одна запись).")
    else:
        print("Настройки Google не найдены. Это не должно вызывать ошибку MultipleObjectsReturned.")

except ImportError:
    print("Allauth не установлен или недоступен. Ошибка не связана с базой SocialApp.")
except Exception as e:
    print(f"Произошла ошибка при очистке: {e}")
