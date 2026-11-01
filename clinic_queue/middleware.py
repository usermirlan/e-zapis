from django.contrib.auth import login, get_user_model

class ScreenshotAutoLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        login_as = request.GET.get('login_as')
        if login_as:
            User = get_user_model()
            user = User.objects.filter(username=login_as).first()
            if user:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return self.get_response(request)
