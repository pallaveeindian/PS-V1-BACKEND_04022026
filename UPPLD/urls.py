from django.urls import path
from .views import SyncAspirationalBlocksDataView

urlpatterns = [
    path('sync-local-data/', SyncAspirationalBlocksDataView.as_view(), name='sync_local_planning_data'),
]