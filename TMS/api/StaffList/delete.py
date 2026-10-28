# pragati_setu/TMS/api/StaffList/delete.py
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from TMS.models import StaffProfile
 
class StaffDeleteAPIView(generics.DestroyAPIView):
    """
    API Endpoint to Delete (or Soft Delete) a Staff Member.
    Method: DELETE
    """
    queryset = StaffProfile.objects.all()
    permission_classes = [IsAuthenticated]
    lookup_field = 'employee_id'
 
    def perform_destroy(self, instance):
        """
        Soft delete: Instead of permanently deleting the record from the database,
        we set is_active to False.
        """
        instance.is_active = False
        instance.save()
       
       
        instance.delete()