from django.contrib import admin

# Отключаем ссылку "ОТКРЫТЬ САЙТ" в Django Admin
admin.site.site_url = None

from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views import defaults as default_views
from django.views.generic import RedirectView
from queue_app import views as app_views

urlpatterns = [
    # Favicon Redirect to solve 404s
    path('favicon.ico', RedirectView.as_view(url='/static/img/favicon.ico')),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]

# Dynamic Allauth URLs inclusion (Survival Mode)
try:
    import allauth
    urlpatterns.append(path('accounts/', include('allauth.urls')))
except ImportError:
    pass

urlpatterns += [
    path('', include('queue_app.urls')),
]

if 'allauth' in settings.INSTALLED_APPS:
    # Adding allauth urls only if the app is installed
    urlpatterns.insert(3, path('accounts/', include('allauth.urls')))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # Тестовые маршруты для аутентичного просмотра страниц ошибок
    urlpatterns += [
        path('test-404/', default_views.page_not_found, {'exception': Exception("Test 404")}),
        path('test-403/', default_views.permission_denied, {'exception': Exception("Test 403")}),
        path('test-500/', default_views.server_error),
    ]

# Ловушка 404 для DEBUG=True (ставим в самый конец!)
urlpatterns += [
    re_path(r'^.*$', app_views.custom_404_view),
]
