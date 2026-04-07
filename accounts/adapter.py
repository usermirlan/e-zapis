from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.conf import settings

class RobustSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Улучшенный адаптер, который предотвращает ошибку MultipleObjectsReturned
    при поиске настроек входа через соцсети.
    """
    def get_app(self, request, provider, **kwargs):
        """
        Ультимативный возврат приложения. Игнорирует базу и настройки,
        чтобы гарантировать работу на PythonAnywhere.
        """
        if provider == 'google':
            return SocialApp(
                provider='google',
                name='Google OAuth',
                client_id='64890493821-ol7u8i3m36lk3l9n0bujdivvj7igll.apps.googleusercontent.com',
                secret='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'
            )
        
        # Fallback для других провайдеров
        try:
            return SocialApp.objects.get(provider=provider, sites__id=settings.SITE_ID)
        except Exception:
            return SocialApp.objects.filter(provider=provider).first()
