from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class RobustSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Совместимый адаптер для allauth 65+.
    - Читает APP из settings
    - Автоматически связывает Google аккаунт с существующим пользователем по email
    - Предотвращает дублирование и ошибки входа
    """

    def get_app(self, request, provider, **kwargs):
        from allauth.socialaccount.models import SocialApp
        try:
            return super().get_app(request, provider, **kwargs)
        except SocialApp.MultipleObjectsReturned:
            return SocialApp.objects.filter(provider=provider).first()
        except Exception:
            return super().get_app(request, provider, **kwargs)

    def pre_social_login(self, request, sociallogin):
        """
        Если пользователь с таким email уже зарегистрирован (например, через форму),
        автоматически привязываем социальный аккаунт Google к существующему пользователю.
        """
        if sociallogin.is_existing:
            return

        # Извлекаем email из Google профиля
        email = None
        if sociallogin.account.extra_data:
            email = sociallogin.account.extra_data.get('email')
        
        if not email and sociallogin.email_addresses:
            for email_addr in sociallogin.email_addresses:
                if email_addr.email:
                    email = email_addr.email
                    break

        if not email:
            return

        # Поиск существующего пользователя
        try:
            user = User.objects.filter(email__iexact=email).first()
            if user:
                sociallogin.connect(request, user)
                logger.info(f"Successfully connected Google account to existing user: {user.email}")
        except Exception as e:
            logger.warning(f"Failed to auto-connect social account: {e}")

    def populate_user(self, request, sociallogin, data):
        """
        Заполняем имя, фамилию и username для нового пользователя.
        """
        user = super().populate_user(request, sociallogin, data)
        extra = sociallogin.account.extra_data or {}

        if not user.first_name and extra.get('given_name'):
            user.first_name = extra.get('given_name')
        if not user.last_name and extra.get('family_name'):
            user.last_name = extra.get('family_name')

        return user

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        """Логируем причину ошибки аутентификации"""
        print(f"\n[GOOGLE AUTH ERROR LOG] Provider: {provider.id if provider else 'None'} | Error: {error} | Exception: {exception} | Extra: {extra_context}\n")
        logger.error(f"Google auth error: error={error}, exception={exception}, extra={extra_context}")
        super().on_authentication_error(request, provider, error=error, exception=exception, extra_context=extra_context)
