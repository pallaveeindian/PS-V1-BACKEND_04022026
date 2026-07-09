import uuid
import random
import string
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction

from TMS.api.serializers import TrainingPartnerCPSerializer
import TMS.models as tms_models 
import core.models as core_models

def generate_custom_th_urid():
    # Example generator for format like: TH_1AN33KN221 (prefix TH_ + 11 alnum)
    body = ''.join(random.choices(string.ascii_uppercase + string.digits, k=11))
    return f"TH_{body}"

class TPCPCreateOneShotView(APIView):
    """
    Atomic endpoint to create a MasterUser and a TrainingPartnerCP simultaneously.
    Rolls back MasterUser creation if TrainingPartnerCP fails.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        auth_user = request.user
        data = request.data

        # 1. Extract payload
        username = data.get('username')
        password = data.get('password')
        name = data.get('name')
        mobile_number = data.get('mobile_number')
        email = data.get('email')
        address = data.get('address')
        partner_id = data.get('partner')
        TH_urid = generate_custom_th_urid()

        if not all([username, password, name]):
            return Response(
                {"error": "username, password, and name are strictly required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Authenticate requesting user
        try:
            master_user = core_models.MasterUser.objects.get(username=auth_user.username)
        except core_models.MasterUser.DoesNotExist:
            return Response({"error": "Invalid requesting user."}, status=status.HTTP_403_FORBIDDEN)

        # 3. Resolve Partner Permissions (Owner, DTP, or Admin)
        partner = tms_models.TrainingPartner.objects.filter(master_user=master_user, is_active=True).first()

        if not partner:
            dtp = tms_models.DistrictTP.objects.filter(master_user=master_user, is_active=True).first()
            if dtp:
                partner = dtp.partner

        if not partner:
            # Fallback for Admin assigning to a specific partner ID
            is_admin = not tms_models.TrainingPartnerCP.objects.filter(master_user=master_user).exists()
            if is_admin and partner_id:
                partner = tms_models.TrainingPartner.objects.filter(id=partner_id, is_active=True).first()

        if not partner:
            return Response(
                {"error": "Training Partner not found or you lack permission."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 4. Prevent duplicate usernames
        if core_models.MasterUser.objects.filter(username=username).exists():
            return Response(
                {"error": "Username already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. ATOMIC TRANSACTION
        try:
            with transaction.atomic():
                # Step A: Create Master User
                new_master_user = core_models.MasterUser(
                    username=username,
                    role_id=data.get('role', 11),  # Default to 11 as mapped in your frontend
                    is_active=True,
                    created_by=master_user,
                    TH_urid=TH_urid,
                )
                new_master_user.password = password  # Storing in cleartext as requested
                new_master_user.save()

                # Step B: Create TPCP Record linked to Master User
                new_tpcp = tms_models.TrainingPartnerCP.objects.create(
                    partner=partner,
                    master_user=new_master_user,
                    name=name,
                    mobile_number=mobile_number,
                    email=email,
                    address=address,
                    created_by=master_user,
                    TH_urid=TH_urid,
                )

            return Response({
                "message": "TC ID created successfully.",
                "tpcp_id": new_tpcp.id,
                "master_user_id": new_master_user.id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )