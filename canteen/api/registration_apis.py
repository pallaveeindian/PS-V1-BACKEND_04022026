# canteen/api/registration_apis.py
import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist

from canteen.models import *
import core.models as core_models

# Canteen Creation View
class CanteenRegistrationView(APIView):
    """
    POST /api/v1/canteen/register/
    One-shot API to create a complete Canteen profile WITH file uploads.
    Accepts multipart/form-data. Stringified JSON for data, Files for licenses.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # Required to accept files

    def post(self, request):
        masteruser = request.user
        try:
            user = core_models.MasterUser.objects.get(username=masteruser.username)
        except core_models.MasterUser.DoesNotExist:
            return Response({"detail": "Authenticated user not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            # 1. Parse the stringified JSON from the form-data
            home_data = json.loads(request.data.get('home', '{}'))
            member_data = json.loads(request.data.get('member', '{}'))
            detail_data = json.loads(request.data.get('detail', '{}'))
            finance_data = json.loads(request.data.get('finance', '{}'))
            model_pc_data = json.loads(request.data.get('model_pc', '{}'))
            
            # Licenses text data (e.g., [{"license_name": "FSSAI"}, {"license_name": "GST"}])
            licenses_data = json.loads(request.data.get('licenses', '[]'))
            
        except json.JSONDecodeError:
            return Response(
                {"detail": "Invalid JSON format in text fields. Ensure data is stringified."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not all([home_data, member_data, detail_data, finance_data]):
            return Response(
                {"detail": "Missing required sections. 'home', 'member', 'detail', and 'finance' are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 2. Atomic block: Locks DB, creates everything, rolls back if any error occurs
            with transaction.atomic():
                home = CanteenHome.objects.create(created_by=user, **home_data)
                
                for member in member_data if isinstance(member_data, list) else [member_data]:
                    CanteenMember.objects.create(canteen_home=home, created_by=user, **member)
                
                if detail_data.get("training_amount") in ["", None]:
                    detail_data.pop("training_amount", None)

                if detail_data.get("training_source") in ["", None]:
                    detail_data.pop("training_source", None)                

                CanteenDetail.objects.create(canteen_home=home, created_by=user, **detail_data)
                CanteenFinance.objects.create(canteen_home=home, created_by=user, **finance_data)
                if model_pc_data:
                    CanteenModelPC.objects.create(
                        canteen_home=home,
                        created_by=user,
                        **model_pc_data
                    )

                # 3. Handle File Uploads securely matching the index
                if isinstance(licenses_data, list):
                    for index, lic_data in enumerate(licenses_data):
                        # The frontend will attach files as 'license_file_0', 'license_file_1', etc.
                        file_key = f'license_file_{index}'
                        uploaded_file = request.FILES.get(file_key)

                        CanteenLicense.objects.create(
                            canteen_home=home,
                            created_by=user,
                            license_name=lic_data.get('license_name'),
                            license_file=uploaded_file # Django handles the secure saving automatically
                        )

            return Response(
                {"detail": "Canteen registered successfully with documents.", "canteen_home_id": home.id},
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            # Any failure (missing required DB field, file system error, etc.) triggers a rollback
            return Response(
                {"detail": f"Registration failed. Transaction rolled back. Error: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

# Canteen Deletion View
class CanteenDeletionView(APIView):
    """
    DELETE /api/v1/canteen/delete/<home_id>/
    (Remains exactly the same as previous step. 
    Soft-deleting a license record leaves the physical file untouched on the server 
    for audit purposes, which is standard practice).
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, home_id):
        masteruser = request.user
        try:
            user = core_models.MasterUser.objects.get(username=masteruser.username)
        except core_models.MasterUser.DoesNotExist:
            return Response({"detail": "Authenticated user not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            with transaction.atomic():
                home = CanteenHome.objects.select_for_update().get(id=home_id, is_active=True)

                for member in home.members.all(): member.delete(by_user=user)
                for detail in home.details.all(): detail.delete(by_user=user)
                for finance in home.finances.all(): finance.delete(by_user=user)
                for license in home.licenses.all(): license.delete(by_user=user)
                for model_pc in home.model_pc.all(): model_pc.delete(by_user=user)
                
                home.delete(by_user=user)

            return Response({"detail": "Canteen and all related data successfully deleted."})
        except CanteenHome.DoesNotExist:
            return Response({"detail": "Active CanteenHome not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": f"Deletion failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Canteen Updation View
class GenericCanteenUpdateView(APIView):
    """
    PATCH /api/v1/canteen/update/
    Supports updating text fields AND file fields dynamically.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # Added to allow file updates

    MODEL_REGISTRY = {
        'CanteenHome': CanteenHome, 'CanteenMember': CanteenMember,
        'CanteenDetail': CanteenDetail, 'CanteenFinance': CanteenFinance,
        'CanteenLicense': CanteenLicense, 'CanteenModelPC': CanteenModelPC,
    }
    FORBIDDEN_FIELDS = {'id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at', 'created_by', 'deleted_by', 'canteen_home'}

    def patch(self, request):
        masteruser = request.user
        try:
            user = core_models.MasterUser.objects.get(username=masteruser.username)
        except core_models.MasterUser.DoesNotExist:
            return Response({"detail": "Authenticated user not found."}, status=status.HTTP_404_NOT_FOUND)

        model_name = request.data.get('model_name')
        row_id = request.data.get('id')
        field = request.data.get('field')

        # Critical: Check if the value is coming from text 'data' or file 'FILES'
        is_file_update = field in request.FILES
        value = request.FILES.get(field) if is_file_update else request.data.get('value')

        if not all([model_name, row_id, field]) or value is None:
            return Response({"detail": "Missing required parameters."}, status=status.HTTP_400_BAD_REQUEST)

        if field in self.FORBIDDEN_FIELDS:
            return Response({"detail": "Modification of restricted field is not allowed."}, status=status.HTTP_403_FORBIDDEN)

        model_class = self.MODEL_REGISTRY.get(model_name)
        if not model_class:
            return Response({"detail": "Invalid model_name provided."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                instance = model_class.objects.select_for_update().get(id=row_id, is_active=True)
                
                if not hasattr(instance, field):
                    return Response({"detail": f"Field '{field}' does not exist."}, status=status.HTTP_400_BAD_REQUEST)

                setattr(instance, field, value)
                instance.updated_by = user
                instance.save(update_fields=[field, 'updated_by', 'updated_at'])

            return Response({
                "detail": "Update successful.",
                "updated_data": {"model": model_name, "id": instance.id, field: str(value) if is_file_update else value}
            })

        except ObjectDoesNotExist:
            return Response({"detail": "Active record not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": f"Update failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)