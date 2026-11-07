# views.py
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from TMS.models import BatchHistory
from .serializers import BatchHistoryCreateSerializer


class BatchHistoryCreateAPIView(generics.CreateAPIView):
    queryset = BatchHistory.objects.all()
    serializer_class = BatchHistoryCreateSerializer
    permission_classes = [IsAuthenticated]

class BatchHistoryListAPIView(generics.ListAPIView):
    queryset = BatchHistory.objects.filter(is_active=True)
    serializer_class = BatchHistoryCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        batch_id = self.request.query_params.get('batch_id', None)
        if batch_id is not None:
            queryset = queryset.filter(batch_id=batch_id)
        return queryset