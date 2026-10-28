# pragati_setu/TMS/api/StaffList/create.py
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from TMS.models import StaffProfile
from .serializers import StaffCreateUpdateSerializer  
 
class StaffCreateAPIView(generics.CreateAPIView):
    """
    API Endpoint to Create/Add a new Staff Member.
    Method: POST
    """
    queryset = StaffProfile.objects.all()
    serializer_class = StaffCreateUpdateSerializer
    permission_classes = [IsAuthenticated]