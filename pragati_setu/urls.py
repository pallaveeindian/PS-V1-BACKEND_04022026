# pragati_setu/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from core.views_health import health

schema_view = get_schema_view(
   openapi.Info(
      title="Pragati Setu API",
      default_version='v1',
      description="API for epSakhi",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(('epSakhi.api.urls', 'epSakhi'), namespace='epSakhi_api')),
    path('api/v1/auth/', include(('core.api.auth_urls', 'core_auth'), namespace='core_auth')),
    path('api/v1/lookups/', include(('core.api.urls', 'core_lookups'), namespace='core_lookups')),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('health', health),
    path("api/v1/tms/", include("TMS.api.urls")),
    path("api/v1/ldms/", include("LDMS.api.urls")),
]

urlpatterns += [
    path(
        "swagger.json",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    path(
        "swagger.yaml",
        schema_view.without_ui(cache_timeout=0),
        name="schema-yaml",
    ),
]