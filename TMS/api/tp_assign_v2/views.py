# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from TMS.models import TrainingPartner
from .serializers import TrainingPartnerSerializer

class TargetedTrainingPartnerAPIView(APIView):
    """
    Retrieves Training Partners based on targets assigned to a specific 
    District, Financial Year, and Training Plan.
    """

    def get(self, request, *args, **kwargs):
        # 1. Extract query parameters
        district_id = request.query_params.get('district_id')
        financial_year = request.query_params.get('financial_year')
        training_plan_id = request.query_params.get('training_plan_id')

        # 2. Validate that all required parameters are present
        if not all([district_id, financial_year, training_plan_id]):
            return Response(
                {
                    "error": "Missing parameters. Please provide 'district_id', "
                             "'financial_year', and 'training_plan_id'."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 3. Query the TrainingPartner model through the 'targets' related_name
            partners = TrainingPartner.objects.filter(
                targets__district_id=district_id,
                targets__financial_year=financial_year,
                targets__training_plan_id=training_plan_id,
                is_active=True
            ).distinct()

            # Note: If your SoftDeleteMixin requires explicit filtering of deleted 
            # objects (e.g., is_deleted=False) and isn't handled by a custom manager, 
            # append it to the filter above: `.filter(..., is_deleted=False)`

            # 4. Serialize and return the data
            serializer = TrainingPartnerSerializer(partners, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except ValueError:
            # Catches invalid ID types (e.g., if a user passes a string instead of an int for IDs)
            return Response(
                {"error": "Invalid data types provided for IDs."},
                status=status.HTTP_400_BAD_REQUEST
            )