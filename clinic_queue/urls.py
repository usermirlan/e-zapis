from django.contrib import admin

# Отключаем ссылку "ОТКРЫТЬ САЙТ" в Django Admin
admin.site.site_url = None

from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views import defaults as default_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('accounts/', include('allauth.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('queue_app.urls')),
]

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
    re_path(r'^.*$', default_views.page_not_found, {'exception': Exception("Page not found")}),
]
