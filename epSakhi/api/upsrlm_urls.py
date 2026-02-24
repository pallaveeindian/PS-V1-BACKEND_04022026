# epSakhi/api/upsrlm_urls.py

from django.urls import path
from .views import (
    # SHG proxy endpoints
    UpsrlmShgListView,
    UpsrlmShgMembersView,
    UpsrlmShgDetailView,
)

urlpatterns = [
    path('upsrlm-shg-list/<int:block_id>/', UpsrlmShgListView.as_view(), name='upsrlm-shg-list'),
    path('upsrlm-shg-members/<str:shg_code>/', UpsrlmShgMembersView.as_view(), name='upsrlm-shg-members'),
    path('upsrlm-shg-detail/<str:shg_code>/', UpsrlmShgDetailView.as_view(), name='upsrlm-shg-detail'),
]
