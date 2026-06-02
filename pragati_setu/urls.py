# pragati_setu/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from core.views_health import health

# Public VIEWS ALL
from TMS.api.homepage_apis.up_at_a_glance import UPAtAGlanceView

# Public VIEWS TMS
from TMS.api.homepage_apis.cadre_select import PublicCadreSelectionSummaryView
from TMS.api.homepage_apis.login_status import PublicFirstLoginSummaryView
from epSakhi.api.homepage_apis.mou_form import PublicDistrictMOUAnalyticsAPIView

schema_view = get_schema_view(
   openapi.Info(
      title="Pragati Setu API",
      default_version='v1',
      description="API Directory for TMS, CRP-EP, and LDMS Apps",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(('epSakhi.api.upsrlm_urls', 'upsrlm'), namespace='upsrlm')),
    path('api/v1/auth/', include(('core.api.auth_urls', 'core_auth'), namespace='core_auth')),
    path('api/v1/lookups/', include(('core.api.urls', 'core_lookups'), namespace='core_lookups')),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('health/', health),
    path("api/v1/tms/", include("TMS.api.urls")),
    path('api/v1/epsakhi/', include(('epSakhi.api.epsakhi_urls', 'epSakhi'), namespace='epSakhi')),
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

    # Public API for Homepage Cadre Selection Summary
    path('api/v1/public/cadre-selection-summary/', PublicCadreSelectionSummaryView.as_view(), name='public-cadre-selection-summary'),    
    # Public API for Homepage First Login & Password Change Summary
    path('api/v1/public/first-login-summary/', PublicFirstLoginSummaryView.as_view(), name='public-first-login-summary'),    
    # Public API for Homepage UP At A Glance Summary
    path('api/v1/public/up-at-a-glance/', UPAtAGlanceView.as_view(), name='public-up-at-a-glance'),
    # Public API for Homepage MOU Analytics
    path(
        "api/v1/public/mou-analytics/",
        PublicDistrictMOUAnalyticsAPIView.as_view(),
        name="public-mou-analytics",
    ),       
]