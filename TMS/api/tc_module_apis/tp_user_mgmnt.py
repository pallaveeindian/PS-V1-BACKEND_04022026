import random
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.models import MasterUser
from TMS.models import (
    TrainingPartner, 
    DistrictTP, 
    TrainingPartnerCP, 
    TrainingPartnerCentre, 
    TPCPToCentre, 
    TMSFirstLoginTracker
)

def get_master_user(request):
    django_user = request.user
    if not django_user or not django_user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    try:
        return MasterUser.objects.get(username=django_user.username)
    except MasterUser.DoesNotExist:
        raise PermissionDenied("Master user not found.")

def get_requester_context(master_user):
    """
    Returns the TP object and DTP object (if applicable) based on requester's role.
    """
    tp_obj = None
    dtp_obj = None

    if master_user.role_id == 4:
        tp_obj = TrainingPartner.objects.filter(master_user=master_user).first()
        if not tp_obj:
            raise PermissionDenied("Training Partner profile not found.")
    elif master_user.role_id == 13:
        dtp_obj = DistrictTP.objects.filter(master_user=master_user).first()
        if not dtp_obj:
            raise PermissionDenied("District TP profile not found.")
        tp_obj = dtp_obj.partner
    else:
        raise PermissionDenied("Only Training Partners and District TPs can perform this action.")
        
    return tp_obj, dtp_obj

class UserManagementAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id=None):
        requester = get_master_user(request)
        tp_obj, dtp_obj = get_requester_context(requester)

        # -------------------------------------------------------------
        # 2) USER DETAIL BEHAVIOR
        # -------------------------------------------------------------
        if user_id:
            try:
                target_user = MasterUser.objects.get(id=user_id)
            except MasterUser.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

            if target_user.role_id == 13:  # Detail for DTP
                if dtp_obj:
                    return Response({"error": "DTPs cannot view other DTP details."}, status=status.HTTP_403_FORBIDDEN)
                
                dtp = DistrictTP.objects.filter(master_user=target_user, partner=tp_obj).first()
                if not dtp:
                    return Response({"error": "DTP not found under your purview."}, status=status.HTTP_404_NOT_FOUND)

                return Response({
                    "id": dtp.id,
                    "master_user_id": dtp.master_user.id,
                    "username": dtp.master_user.username,
                    "role_id": target_user.role_id,
                    "district_id": dtp.district_id,
                    "district_name_en": dtp.district.district_name_en,
                    "is_active_dtp": dtp.is_active_dtp,
                    "created_at": target_user.created_at
                }, status=status.HTTP_200_OK)

            elif target_user.role_id == 11:  # Detail for TPCP
                tpcp = TrainingPartnerCP.objects.filter(master_user=target_user, partner=tp_obj).first()
                if not tpcp:
                    return Response({"error": "TPCP not found under your purview."}, status=status.HTTP_404_NOT_FOUND)

                # Fetch assigned centres
                assigned_centres = TrainingPartnerCentre.objects.filter(
                    is_active=True,
                    tpcptocentre__contact_person=tpcp,
                    tpcptocentre__is_active=True,
                ).distinct()
                if dtp_obj:
                    assigned_centres = assigned_centres.filter(district=dtp_obj.district)

                return Response({
                    "id": tpcp.id,
                    "master_user_id": tpcp.master_user.id,
                    "username": tpcp.master_user.username,
                    "role_id": target_user.role_id,
                    "name": tpcp.name,
                    "email": tpcp.email,
                    "mobile_number": tpcp.mobile_number,
                    "address": tpcp.address,
                    "assigned_centres": list(assigned_centres.values('id', 'venue_name', 'district__district_name_en'))
                }, status=status.HTTP_200_OK)

            return Response({"error": "Invalid user role requested."}, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------------------
        # 1) USERS LIST BEHAVIOR
        # -------------------------------------------------------------
        target_role = request.query_params.get('type', 'tpcp')

        if target_role == 'dtp':
            if dtp_obj:
                return Response({"error": "DTPs cannot list other DTPs."}, status=status.HTTP_403_FORBIDDEN)
            
            dtps = DistrictTP.objects.filter(partner=tp_obj, is_active_dtp=True).select_related('master_user', 'district')
            results = []
            for dtp in dtps:
                # Count centres in this DTP's district
                centre_count = TrainingPartnerCentre.objects.filter(
                    partner=tp_obj,
                    district=dtp.district,
                    is_active=True,
                ).count()
                results.append({
                    "id": dtp.id,
                    "master_user_id": dtp.master_user.id if dtp.master_user else None,
                    "username": dtp.master_user.username if dtp.master_user else None,
                    "district_id": dtp.district_id,
                    "district_name_en": dtp.district.district_name_en if dtp.district else None,
                    "centre_count": centre_count
                })
            return Response(results, status=status.HTTP_200_OK)

        elif target_role == 'tpcp':
            if dtp_obj:
                # DTP viewing TPCPs -> Only active TPCPs mapped to active centres in DTP's district
                tpcps = TrainingPartnerCP.objects.filter(
                    partner=tp_obj,
                    is_active=True,
                    tpcptocentre__is_active=True,
                    tpcptocentre__allocated_centre__is_active=True,
                    tpcptocentre__allocated_centre__district=dtp_obj.district,
                ).distinct().select_related('master_user')
            else:
                # TP viewing all active TPCPs
                tpcps = TrainingPartnerCP.objects.filter(
                    partner=tp_obj,
                    is_active=True,
                ).select_related('master_user')

            results = []
            for tpcp in tpcps:
                centres = TrainingPartnerCentre.objects.filter(
                    is_active=True,
                    tpcptocentre__contact_person=tpcp,
                    tpcptocentre__is_active=True,
                ).distinct()
                if dtp_obj:
                    centres = centres.filter(district=dtp_obj.district)
                    
                results.append({
                    "id": tpcp.id,
                    "master_user_id": tpcp.master_user.id if tpcp.master_user else None,
                    "username": tpcp.master_user.username if tpcp.master_user else None,
                    "name": tpcp.name,
                    "assigned_centres": list(centres.values('id', 'venue_name', 'district__district_name_en'))
                })
            return Response(results, status=status.HTTP_200_OK)

        return Response({"error": "Invalid type param. Use 'dtp' or 'tpcp'."}, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, user_id):
        # -------------------------------------------------------------
        # 3) UPDATE BEHAVIOR (Username & Centres)
        # -------------------------------------------------------------
        requester = get_master_user(request)
        tp_obj, dtp_obj = get_requester_context(requester)

        try:
            target_user = MasterUser.objects.get(id=user_id)
        except MasterUser.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        new_username = request.data.get('username')
        centre_ids = request.data.get('centre_ids')  # Expecting a list of IDs

        with transaction.atomic():
            # Update Username
            if new_username and new_username != target_user.username:
                if MasterUser.objects.filter(username=new_username).exists():
                    return Response({"error": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)
                target_user.username = new_username
                target_user.updated_at = timezone.now()
                target_user.updated_by = requester
                target_user.save()

            # Update assigned centres (Only applicable for TPCPs)
            if centre_ids is not None and target_user.role_id == 11:
                tpcp = TrainingPartnerCP.objects.filter(master_user=target_user, partner=tp_obj).first()
                if not tpcp:
                    return Response({"error": "TPCP not found under your purview."}, status=status.HTTP_404_NOT_FOUND)

                # Validate provided centres
                valid_centres = TrainingPartnerCentre.objects.filter(partner=tp_obj, id__in=centre_ids)
                if dtp_obj:
                    valid_centres = valid_centres.filter(district=dtp_obj.district)
                
                valid_centre_ids = set(valid_centres.values_list('id', flat=True))

                # Clear old mappings
                if dtp_obj:
                    # DTP can only overwrite mappings within their own district
                    TPCPToCentre.objects.filter(contact_person=tpcp, allocated_centre__district=dtp_obj.district).delete()
                else:
                    # TP overwrites all
                    TPCPToCentre.objects.filter(contact_person=tpcp).delete()

                # Create new mappings
                new_mappings = [
                    TPCPToCentre(contact_person=tpcp, allocated_centre_id=cid) 
                    for cid in valid_centre_ids
                ]
                TPCPToCentre.objects.bulk_create(new_mappings)

        return Response({"message": "User updated successfully."}, status=status.HTTP_200_OK)

    def delete(self, request, user_id):
        # -------------------------------------------------------------
        # 4) DELETE BEHAVIOR
        # -------------------------------------------------------------
        requester = get_master_user(request)
        tp_obj, dtp_obj = get_requester_context(requester)

        try:
            target_user = MasterUser.objects.get(id=user_id)
        except MasterUser.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            if target_user.role_id == 13:
                if dtp_obj:
                    return Response({"error": "DTP cannot delete DTPs."}, status=status.HTTP_403_FORBIDDEN)
                DistrictTP.objects.filter(master_user=target_user, partner=tp_obj).delete()

            elif target_user.role_id == 11:
                tpcp = TrainingPartnerCP.objects.filter(master_user=target_user, partner=tp_obj).first()
                if not tpcp:
                    return Response({"error": "TPCP not found."}, status=status.HTTP_404_NOT_FOUND)
                tpcp.delete()

            # Soft Delete MasterUser
            target_user.is_active = 0
            target_user.deleted_at = timezone.now()
            target_user.deleted_by = requester
            target_user.save()

        return Response({"message": "User deleted successfully."}, status=status.HTTP_200_OK)


class UserPasswordResetAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        # -------------------------------------------------------------
        # 5) RESET PASSWORD BEHAVIOR
        # -------------------------------------------------------------
        requester = get_master_user(request)
        tp_obj, dtp_obj = get_requester_context(requester)

        try:
            target_user = MasterUser.objects.get(id=user_id)
        except MasterUser.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Permission check
        if target_user.role_id == 13 and dtp_obj:
             return Response({"error": "DTP cannot reset DTP passwords."}, status=status.HTTP_403_FORBIDDEN)

        if not (DistrictTP.objects.filter(master_user=target_user, partner=tp_obj).exists() or 
                TrainingPartnerCP.objects.filter(master_user=target_user, partner=tp_obj).exists()):
            return Response({"error": "User not under your purview."}, status=status.HTTP_403_FORBIDDEN)

        # Generate Password
        tp_short = tp_obj.tp_short_name.strip().replace(" ", "") if tp_obj.tp_short_name else f"TP{tp_obj.id}"
        rand_num = random.randint(1000, 9999)
        new_cleartext_password = f"{tp_short}@{rand_num}"

        with transaction.atomic():
            target_user.password = make_password(new_cleartext_password)
            target_user.pass_updated_at = timezone.now()
            target_user.pass_updated_by = requester
            target_user.save()

            # Delete TMSFirstLoginTracker to force change password on next login
            TMSFirstLoginTracker.objects.filter(master_user=target_user).delete()

        return Response({
            "message": "Password reset successfully.",
            "new_password": new_cleartext_password
        }, status=status.HTTP_200_OK)