# pragati_setu/TMS/api/StaffList/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from rest_framework import generics
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from TMS.models import StaffProfile
from .serializers import *

class StaffListAPIView(generics.ListAPIView):
    """
    API Endpoint to List all Active Staff Members.
    Includes Search and Filtering capabilities.
    """
    serializer_class = StaffListSerializer
    
    # 1. Backends for Filtering, Searching, and Sorting
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    
    # 2. Search Fields (Text-based searching like ?search=abhishek)
    search_fields = [
        'mobile', 
        'email', 
        'employee_id', 
        'full_name'
    ]
    
    # 3. Filter Fields (Exact match filtering like ?district=12&gender=Male)
    # Note: DRF automatically maps 'district' to 'district_id' for Foreign Keys
    filterset_fields = [
        'designation', 
        'theme', 
        'employment_type', 
        'gender', 
        'district', 
        'block', 
        'social_category'
    ]
    
    # Optional: Default ordering
    ordering_fields = ['created_at', 'full_name']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Only return active staff. Use select_related to optimize the DB query
        by fetching the basic related names in a single SQL JOIN.
        """
        return StaffProfile.objects.filter(is_active=True).select_related(
            'theme', 'district', 'block'
        )


class StaffDetailAPIView(generics.RetrieveAPIView):
    """
    API Endpoint to get WHOLE NESTED details of a specific staff member.
    Looks up via 'employee_id' instead of the default 'id' PK.
    """
    serializer_class = StaffDetailSerializer
    
    # Look up by employee_id instead of auto-increment ID
    lookup_field = 'employee_id'

    def get_queryset(self):
        """
        Use select_related to fetch ALL nested foreign keys in a single, 
        highly-optimized SQL query so it doesn't slam the database.
        """
        return StaffProfile.objects.filter(is_active=True).select_related(
            'theme', 
            'district', 
            'block', 
            'bank', 
            'bank_branch', 
            'bank_ifsc'
        )

class StaffFilterOptionsAPIView(APIView):
    """
    API Endpoint to fetch unique values for Staff filter dropdowns.
    Returns distinct designations, employment types, and social categories.
    """
    # Assuming authenticated users only, adjust permissions as needed for your app
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Get Distinct Designations (Exclude nulls and empty strings, sort alphabetically)
        designations = StaffProfile.objects.filter(is_active=True)\
            .exclude(designation__isnull=True)\
            .exclude(designation__exact='')\
            .values_list('designation', flat=True)\
            .distinct()\
            .order_by('designation')

        # 2. Get Distinct Employment Types
        employment_types = StaffProfile.objects.filter(is_active=True)\
            .exclude(employment_type__isnull=True)\
            .exclude(employment_type__exact='')\
            .values_list('employment_type', flat=True)\
            .distinct()\
            .order_by('employment_type')

        # 3. Get Distinct Social Categories
        social_categories = StaffProfile.objects.filter(is_active=True)\
            .exclude(social_category__isnull=True)\
            .exclude(social_category__exact='')\
            .values_list('social_category', flat=True)\
            .distinct()\
            .order_by('social_category')

        # 4. Return as a clean JSON dictionary
        return Response({
            "designations": list(designations),
            "employment_types": list(employment_types),
            "social_categories": list(social_categories)
        })        