from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.conf import settings

class RobustSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Улучшенный адаптер, который предотвращает ошибку MultipleObjectsReturned
    при поиске настроек входа через соцсети.
    """
    def get_app(self, request, provider, **kwargs):
        config = kwargs.get('config')
        if config:
            return SocialApp(provider=provider, **config)
        
        # Пытаемся найти приложение стандартным способом
        try:
            return SocialApp.objects.get(provider=provider, sites__id=settings.SITE_ID)
        except SocialApp.MultipleObjectsReturned:
            # Если найдено несколько (баг базы или дубли), просто берем первое рабочее
            return SocialApp.objects.filter(provider=provider, sites__id=settings.SITE_ID).first()
        except SocialApp.DoesNotExist:
            # Если привязка к сайту не найдена, пробуем найти любое приложение для этого провайдера
            app = SocialApp.objects.filter(provider=provider).first()
            if app:
                return app
            raise
