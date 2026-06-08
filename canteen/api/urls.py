# canteen/api/urls.py
from django.urls import path, include
from canteen.api.registration_apis import *
from canteen.api.views import *

# Listing APIs
default_urls = [
    path('canteen-list/', CanteenListView.as_view(), name='canteen-list'),
    path('canteen-detail/<int:home_id>/', CanteenDetailView.as_view(), name='canteen-detail'),
]

# One-shot APIs
oneshot_urls = [
    path('canteen/create/', CanteenRegistrationView.as_view(), name='canteen-create'),
    path('canteen/delete/', CanteenDeletionView.as_view(), name='canteen-delete'),
    path('canteen/update/', GenericCanteenUpdateView.as_view(), name='canteen-update'),
]

urlpatterns = [
    *default_urls,
    *oneshot_urls
]
