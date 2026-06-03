from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.db.models import OuterRef, Subquery

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from TMS.models import TMSFirstLoginTracker
from core import models as core_models

# User Account Management API
class ManageUserView(APIView):

    def _verify_smmu_access(self, request):
        auth_user = request.user

        if not auth_user or auth_user.is_anonymous:
            raise PermissionDenied(
                "Authentication credentials were not provided."
            )

        master_user = (
            core_models.MasterUser.objects
            .select_related("role")
            .filter(username=auth_user.username)
            .first()
        )

        if not master_user:
            raise PermissionDenied("Invalid profile mapping.")

        role_id = getattr(master_user, "role_id", None)

        role_name = (
            getattr(master_user.role, "name", "")
            if master_user.role else ""
        ).upper()

        is_smmu = (
            role_id == 3
            or "SMMU" in role_name
        )

        is_dmmu = (
            role_id == 2
            or "DMMU" in role_name
        )

        if not (is_smmu or is_dmmu):
            raise PermissionDenied(
                "Only SMMU/DMMU users can perform this action."
            )

        return master_user

    @transaction.atomic
    def post(self, request):

        acting_user = self._verify_smmu_access(request)

        user_id = request.data.get("user_id")

        if not user_id:
            return Response(
                {"message": "user_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        target_user = (
            core_models.MasterUser.objects
            .select_related("role")
            .filter(id=user_id)
            .first()
        )

        if not target_user:
            return Response(
                {"message": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # --------------------------------------------------
        # USERNAME CHANGE
        # --------------------------------------------------

        username = request.data.get("username")

        if username:

            username_exists = (
                core_models.MasterUser.objects
                .filter(username=username)
                .exclude(id=target_user.id)
                .exists()
            )

            if username_exists:
                return Response(
                    {"message": "Username already exists"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            target_user.username = username

        # --------------------------------------------------
        # ACTIVATE / DEACTIVATE
        # --------------------------------------------------

        if "is_active" in request.data:
            target_user.is_active = request.data.get("is_active")

        # --------------------------------------------------
        # RECOVERY DETAILS
        # --------------------------------------------------

        if "recovery_email" in request.data:
            target_user.recovery_email = request.data.get(
                "recovery_email"
            )

        if "recovery_mobile" in request.data:
            target_user.recovery_mobile = request.data.get(
                "recovery_mobile"
            )

        # --------------------------------------------------
        # UNLOCK ACCOUNT
        # --------------------------------------------------

        unlock_account = request.data.get(
            "unlock_account",
            False
        )

        if unlock_account:

            target_user.is_locked = 0
            target_user.locked_on = None
            target_user.pass_attempt_no = 0

        # --------------------------------------------------
        # PASSWORD RESET
        # --------------------------------------------------

        reset_password = request.data.get(
            "reset_password",
            False
        )

        generated_password = None

        if reset_password:

            geo_scope = (
                core_models.MasterGeoUserScope.objects
                .filter(
                    user_id=target_user.id,
                    is_active=1
                )
                .first()
            )

            if not geo_scope:
                return Response(
                    {
                        "message":
                        "User geo mapping not found."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            role_id = getattr(
                target_user,
                "role_id",
                None
            )

            # -----------------------------------
            # BMMU PASSWORD
            # <district first 2 letters>
            # <block>@admin
            # -----------------------------------

            if role_id == 1:

                district = (
                    core_models.MasterDistrict.objects
                    .filter(
                        district_id=geo_scope.district_id
                    )
                    .first()
                )

                block = (
                    core_models.MasterBlock.objects
                    .filter(
                        block_id=geo_scope.block_id
                    )
                    .first()
                )

                if not district or not block:
                    return Response(
                        {
                            "message":
                            "District/Block mapping missing."
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                district_prefix = (
                    district.district_name_en[:2]
                    .strip()
                )

                generated_password = (
                    f"{district_prefix}"
                    f"{block.block_name_en}"
                    f"@admin"
                )

            # -----------------------------------
            # DMMU PASSWORD
            # district@admin
            # -----------------------------------

            elif role_id == 2:

                district = (
                    core_models.MasterDistrict.objects
                    .filter(
                        district_id=geo_scope.district_id
                    )
                    .first()
                )

                if not district:
                    return Response(
                        {
                            "message":
                            "District mapping missing."
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                generated_password = (
                    f"{district.district_name_en}"
                    f"@admin"
                )

            else:

                return Response(
                    {
                        "message":
                        "Password reset only supported for BMMU/DMMU users."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            target_user.password = generated_password

            target_user.pass_attempt_no = 0
            target_user.is_locked = 0
            target_user.locked_on = None

            TMSFirstLoginTracker.objects.update_or_create(
                master_user=target_user,
                defaults={
                    "must_change_password": True
                }
            )            
            
        # --------------------------------------------------
        # AUDIT
        # --------------------------------------------------

        target_user.updated_by = acting_user
        target_user.save()

        response_data = {
            "message": "User updated successfully",
            "user_id": target_user.id
        }

        if generated_password:
            response_data[
                "default_password"
            ] = generated_password

        return Response(
            response_data,
            status=status.HTTP_200_OK
        )

# DMMU - BMMU User Listing API
class BMMUUserListingView(APIView):
    """
    Lists all BMMU users under the logged-in DMMU user's district.

    Returns:
    - username
    - block_name_en
    - district_name_en
    - is_active
    - last_active_on
    - is_locked
    - locked_on
    - is_suspended
    - suspended_on

    Query Params:
    - page (default=1)
    - page_size (default=50)
    """

    def _verify_dmmu_access(self, request):
        auth_user = request.user

        if not auth_user or auth_user.is_anonymous:
            raise PermissionDenied(
                "Authentication credentials were not provided."
            )

        master_user = (
            core_models.MasterUser.objects
            .select_related("role")
            .filter(username=auth_user.username)
            .first()
        )

        if not master_user:
            raise PermissionDenied("Invalid profile mapping.")

        role_id = getattr(master_user, "role_id", None)

        role_name = (
            getattr(master_user.role, "name", "")
            if master_user.role
            else ""
        ).upper()

        is_dmmu_role = (
            role_id == 2
            or "DMMU" in role_name
        )

        if not is_dmmu_role:
            raise PermissionDenied(
                "Access Denied: Only DMMU users can access this endpoint."
            )

        return master_user

    def get(self, request):

        dmmu_user = self._verify_dmmu_access(request)

        # --------------------------------------------------
        # Get DMMU district
        # --------------------------------------------------
        dmmu_scope = (
            core_models.MasterGeoUserScope.objects
            .filter(
                user_id=dmmu_user.id,
                is_active=1
            )
            .first()
        )

        if not dmmu_scope or not dmmu_scope.district_id:
            return Response(
                {"message": "District mapping not found."},
                status=status.HTTP_400_BAD_REQUEST
            )

        district_id = dmmu_scope.district_id

        # --------------------------------------------------
        # Pagination
        # --------------------------------------------------
        try:
            page = int(request.GET.get("page", 1))
        except Exception:
            page = 1

        try:
            page_size = int(request.GET.get("page_size", 10))
        except Exception:
            page_size = 10

        page_size = min(page_size, 500)

        offset = (page - 1) * page_size

        # --------------------------------------------------
        # Subqueries for user scope
        # --------------------------------------------------
        scope_qs = (
            core_models.MasterGeoUserScope.objects
            .filter(
                user_id=OuterRef("id"),
                is_active=1
            )
            .order_by("id")
        )

        users_qs = (
            core_models.MasterUser.objects
            .filter(
                role_id=1,
                deleted_at__isnull=True
            )
            .annotate(
                scope_block_id=Subquery(
                    scope_qs.values("block_id")[:1]
                ),
                scope_district_id=Subquery(
                    scope_qs.values("district_id")[:1]
                ),
            )
            .filter(
                scope_district_id=district_id
            )
            .order_by("username")
        )

        total_count = users_qs.count()

        users = users_qs[offset:offset + page_size]

        # --------------------------------------------------
        # Bulk fetch block/district names
        # --------------------------------------------------
        block_ids = {
            u.scope_block_id
            for u in users
            if u.scope_block_id
        }

        district_ids = {
            u.scope_district_id
            for u in users
            if u.scope_district_id
        }

        block_map = {
            b.block_id: b.block_name_en
            for b in core_models.MasterBlock.objects.filter(
                block_id__in=block_ids
            )
        }

        district_map = {
            d.district_id: d.district_name_en
            for d in core_models.MasterDistrict.objects.filter(
                district_id__in=district_ids
            )
        }

        results = []

        for user in users:
            results.append({
                "user_id": user.id,
                "username": user.username,
                "block_name_en": block_map.get(
                    user.scope_block_id
                ),
                "district_name_en": district_map.get(
                    user.scope_district_id
                ),
                "is_active": user.is_active,
                "last_active_on": user.last_active_on,
                "is_locked": user.is_locked,
                "locked_on": user.locked_on,
                "is_suspended": user.is_suspended,
                "suspended_on": user.suspended_on,
            })

        return Response({
            "count": total_count,
            "current_page": page,
            "page_size": page_size,
            "total_pages": (
                (total_count + page_size - 1)
                // page_size
            ),
            "results": results
        })

# SMMU - DMMU User Listing API
class DMMUDistrictListingView(APIView):
    """
    SMMU only API

    Returns all districts and their mapped DMMU users.

    Query Params:
        page
        page_size
        search

    Response:
    [
        {
            "user_id": 10,
            "username": "dmmu_lucknow",
            "district_id": 123,
            "district_name_en": "Lucknow",
            "is_active": 1,
            "last_active_on": "...",
            "is_locked": 0,
            "locked_on": null,
            "is_suspended": 0,
            "suspended_on": null
        }
    ]
    """

    def _verify_smmu_access(self, request):
        auth_user = request.user

        if not auth_user or auth_user.is_anonymous:
            raise PermissionDenied(
                "Authentication credentials were not provided."
            )

        master_user = (
            core_models.MasterUser.objects
            .select_related("role")
            .filter(username=auth_user.username)
            .first()
        )

        if not master_user:
            raise PermissionDenied("Invalid profile mapping.")

        role_id = getattr(master_user, "role_id", None)

        role_name = (
            getattr(master_user.role, "name", "")
            if master_user.role else ""
        ).upper()

        is_smmu_role = (
            role_id == 3
            or "SMMU" in role_name
        )

        if not is_smmu_role:
            raise PermissionDenied(
                "Access Denied: Only SMMU users can access this endpoint."
            )

        return master_user

    def get(self, request):

        self._verify_smmu_access(request)

        try:
            page = int(request.GET.get("page", 1))
        except Exception:
            page = 1

        try:
            page_size = int(request.GET.get("page_size", 10))
        except Exception:
            page_size = 10

        page_size = min(page_size, 500)

        search = request.GET.get("search", "").strip()

        offset = (page - 1) * page_size

        # --------------------------------------------------
        # Geo Scope Subquery
        # --------------------------------------------------

        scope_qs = (
            core_models.MasterGeoUserScope.objects
            .filter(
                user_id=OuterRef("id"),
                is_active=1
            )
            .order_by("id")
        )

        queryset = (
            core_models.MasterUser.objects
            .filter(
                role_id=2,
                deleted_at__isnull=True
            )
            .annotate(
                scope_district_id=Subquery(
                    scope_qs.values("district_id")[:1]
                )
            )
            .filter(
                scope_district_id__isnull=False
            )
            .order_by("username")
        )

        if search:
            queryset = queryset.filter(
                username__icontains=search
            )

        total_count = queryset.count()

        users = queryset[offset:offset + page_size]

        district_ids = {
            user.scope_district_id
            for user in users
            if user.scope_district_id
        }

        district_map = {
            district.district_id: district.district_name_en
            for district in (
                core_models.MasterDistrict.objects.filter(
                    district_id__in=district_ids
                )
            )
        }

        results = []

        for user in users:
            results.append({
                "user_id": user.id,
                "username": user.username,
                "district_id": user.scope_district_id,
                "district_name_en": district_map.get(
                    user.scope_district_id
                ),
                "is_active": user.is_active,
                "last_active_on": user.last_active_on,
                "is_locked": user.is_locked,
                "locked_on": user.locked_on,
                "is_suspended": user.is_suspended,
                "suspended_on": user.suspended_on,
            })

        return Response({
            "count": total_count,
            "current_page": page,
            "page_size": page_size,
            "total_pages": (
                (total_count + page_size - 1)
                // page_size
            ),
            "results": results
        })        