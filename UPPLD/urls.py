from django.urls import path
from .views import (
    SyncAspirationalBlocksDataView,
)
from .api.views import AspirationalBlockAchievementListView

urlpatterns = [
    # Data Push / Sync endpoint:
    # POST /api/v1/uppld/sync-local-data/
    path('sync-local-data/', SyncAspirationalBlocksDataView.as_view(), name='sync_local_planning_data'),

    # Listing & Filter endpoint:
    # GET /api/v1/uppld/achievements/?year=2026-27&month=9&prog_code=0511
    path('achievements/', AspirationalBlockAchievementListView.as_view(), name='aspirational_achievements_list'),
]