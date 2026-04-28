from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings


class RobustSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Совместимый адаптер для allauth 65+.
    Использует встроенный механизм allauth для чтения APP из SOCIALACCOUNT_PROVIDERS,
    и только при ошибке MultipleObjectsReturned — берёт первую запись из БД.
    """

    def get_app(self, request, provider, **kwargs):
        """
        Сначала пробуем стандартный allauth 65+ механизм (читает APP из settings).
        Если возникает MultipleObjectsReturned — берём первую запись.
        """
        from allauth.socialaccount.models import SocialApp

        try:
            # allauth 65+ сам читает APP из SOCIALACCOUNT_PROVIDERS — не трогаем
            return super().get_app(request, provider, **kwargs)
        except SocialApp.MultipleObjectsReturned:
            return SocialApp.objects.filter(provider=provider).first()
        except Exception:
            return super().get_app(request, provider, **kwargs)

