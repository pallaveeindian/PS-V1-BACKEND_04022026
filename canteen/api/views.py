from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import F

from canteen.models import *

# Canteen List View with Filtering and Flattened Output
class CanteenListView(APIView):
    """
    GET /api/v1/canteen/list/
    Lists all active registered canteens with flattened geographic and detail fields.
    Includes filtering by geography, types, and date ranges.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Base Queryset: Only active CanteenHomes
        qs = CanteenHome.objects.filter(is_active=True)

        # 2. Apply Filters from query parameters
        params = request.query_params

        if params.get('district_id'):
            qs = qs.filter(district_id=params['district_id'])
        if params.get('block_id'):
            qs = qs.filter(block_id=params['block_id'])
        if params.get('panchayat_id'):
            qs = qs.filter(panchayat_id=params['panchayat_id'])
        if params.get('village_id'):
            qs = qs.filter(village_id=params['village_id'])
            
        if params.get('canteen_type'):
            qs = qs.filter(canteen_type__icontains=params['canteen_type'])
            
        # Reverse relation filtering (details is the related_name)
        if params.get('food_type'):
            qs = qs.filter(details__food_type__icontains=params['food_type'])
            
        # Date of Establishment Filters (Exact and Range)
        if params.get('date_of_establishment'):
            qs = qs.filter(details__date_of_establishment=params['date_of_establishment'])
        if params.get('date_from'):
            qs = qs.filter(details__date_of_establishment__gte=params['date_from'])
        if params.get('date_to'):
            qs = qs.filter(details__date_of_establishment__lte=params['date_to'])

        # 3. Flatten and Select Specific Fields
        # We use F() expressions to pull fields from related tables and rename them
        # Note: 'details' is a related_name, assuming 1 Detail per Home as per registration logic.
        flattened_qs = (
            qs.annotate(
                district_name_en=F('district__district_name_en'),
                block_name_en=F('block__block_name_en'),
                panchayat_name_en=F('panchayat__panchayat_name_en'),
                village_name_english=F('village__village_name_english'),
                canteen_name=F('details__canteen_name'),
                food_type=F('details__food_type'),
                date_of_establishment=F('details__date_of_establishment')
            )
            .values(
                'id',
                'TH_urid',
                'canteen_type',
                'district_id',
                'district_name_en',
                'block_id',
                'block_name_en',
                'panchayat_id',
                'panchayat_name_en',
                'village_id',
                'village_name_english',
                'canteen_name',
                'food_type',
                'date_of_establishment'
            )
            .order_by('-created_at')
        )

        # To avoid duplicate rows if there happen to be multiple details by mistake, we call distinct()
        data = list(flattened_qs.distinct())

        return Response({
            "meta": {
                "total": len(data)
            },
            "data": data
        }, status=status.HTTP_200_OK)

# Canteen Detail View
class CanteenDetailView(APIView):
    """
    GET /api/v1/canteen/detail/<home_id>/
    Fetches the complete nested profile of a specific Canteen.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, home_id):
        try:
            home = CanteenHome.objects.get(id=home_id, is_active=True)
            
            # Helper function to convert model instances to dicts, filtering out active rows
            def serialize_qs(queryset, fields=None):
                return list(queryset.filter(is_active=True).values(*fields) if fields else queryset.filter(is_active=True).values())

            # Construct the complete nested dictionary
            response_data = {
                "home": {
                    "id": home.id,
                    "TH_urid": home.TH_urid,
                    "canteen_type": home.canteen_type,
                    "district_id": home.district_id,
                    "block_id": home.block_id,
                    "panchayat_id": home.panchayat_id,
                    "village_id": home.village_id,
                    "created_at": home.created_at
                },
                # Using .first() since registration enforces 1 per home
                "member": serialize_qs(home.members.all())[0] if home.members.filter(is_active=True).exists() else None,
                "detail": serialize_qs(home.details.all())[0] if home.details.filter(is_active=True).exists() else None,
                "finance": serialize_qs(home.finances.all())[0] if home.finances.filter(is_active=True).exists() else None,
                "model_pc": serialize_qs(home.model_pc.all())[0] if home.model_pc.filter(is_active=True).exists() else None,
                # Licenses can be multiple
                "licenses": serialize_qs(home.licenses.all(), ['id', 'license_name', 'license_file', 'created_at'])
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except CanteenHome.DoesNotExist:
            return Response({"detail": "Active Canteen not found."}, status=status.HTTP_404_NOT_FOUND)


