# support/urls.py
from django.urls import path
from .views import (
    TicketCreateAPIView,
    TicketDeleteAPIView,
    TicketListAPIView,
    TicketDetailAPIView
)

urlpatterns = [
    # PUBLIC API
    path('tickets/create/', TicketCreateAPIView.as_view(), name='ticket-create'),
    
    # AUTH-BASED APIs
    path('tickets/list/', TicketListAPIView.as_view(), name='ticket-list'),
    path('tickets/<str:ticket_code>/', TicketDetailAPIView.as_view(), name='ticket-detail'),
    path('tickets/delete/<str:ticket_code>/', TicketDeleteAPIView.as_view(), name='ticket-delete'),
]