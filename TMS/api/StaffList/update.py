# pragati_setu/TMS/api/StaffList/update.py
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from TMS.models import StaffProfile
from .serializers import StaffCreateUpdateSerializer
 
class StaffUpdateAPIView(generics.UpdateAPIView):
    """
    API Endpoint to Update an existing Staff Member.
    Method: PUT (Whole object update) or PATCH (Partial fields update)
    """
    queryset = StaffProfile.objects.all()
    serializer_class = StaffCreateUpdateSerializer
    permission_classes = [IsAuthenticated]
   
   
    lookup_field = 'employee_id'