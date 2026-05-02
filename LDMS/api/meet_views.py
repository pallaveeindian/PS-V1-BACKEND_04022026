from rest_framework import viewsets, status
from rest_framework.exceptions import PermissionDenied
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated

from core.models import *
from LDMS.models import *
from .serializers import *

class BaseMeetingViewSet(viewsets.ModelViewSet):
    """Base ViewSet to handle common User and GeoScope fetching."""
    permission_classes = [IsAuthenticated]
    
    def get_master_user(self):
        django_user = self.request.user
        master_user = MasterUser.objects.filter(username=django_user.username).first()
        if not master_user:
            raise PermissionDenied("Master user not found.")
        return master_user

    def get_user_scope(self, master_user):
        scope = MasterGeoUserScope.objects.filter(user_id=master_user.id, is_active=1).first()
        if not scope:
            raise PermissionDenied("No active geographical mapping found for this user.")
        return scope

    def perform_destroy(self, instance):
        # Trigger your SoftDeleteMixin logic, passing the user who deleted it
        instance.delete(by_user=self.get_master_user())


# ----------------------------------------
# DLCC ViewSet (DMMU)
# ----------------------------------------
class DLCCMeetingViewSet(BaseMeetingViewSet):
    serializer_class = DLCCMeetingSerializer

    def get_queryset(self):
        master_user = self.get_master_user()
        scope = self.get_user_scope(master_user)
        role = master_user.role_id

        # ---------------- BASE QUERY ----------------
        qs = DLCC_Meeting.objects.filter(is_active=True)

        # ---------------- ROLE FILTER ----------------
        if role == 3:  # SMMU → FULL ACCESS
            district_id = self.request.query_params.get('district')
            if district_id:
                qs = qs.filter(district_id=district_id)

        else:
            # DMMU / others → LOCKED
            if not scope.district_id:
                raise PermissionDenied("User is not mapped to a specific district.")
            qs = qs.filter(district_id=scope.district_id)

        # ---------------- DATE FILTERS ----------------
        meeting_month = self.request.query_params.get('meeting_month')
        if meeting_month:
            parts = meeting_month.split('-')
            if len(parts) == 2:
                qs = qs.filter(
                    meeting_date__year=parts[0],
                    meeting_date__month=parts[1]
                )

        meeting_year = self.request.query_params.get('meeting_year')
        if meeting_year:
            qs = qs.filter(meeting_date__year=meeting_year)

        meeting_date = self.request.query_params.get('meeting_date')
        if meeting_date:
            qs = qs.filter(meeting_date=meeting_date)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        master_user = self.get_master_user()
        scope = self.get_user_scope(master_user)

        is_uploaded = True if self.request.FILES.get('mom') else False
        
        serializer.save(
            created_by=master_user,
            district_id=scope.district_id,
            is_uploaded=is_uploaded
        )

    def perform_update(self, serializer):
        master_user = self.get_master_user()
        instance = serializer.save(updated_by=master_user, updated_at=timezone.now())
        
        # Toggle upload status if a file was provided
        if instance.mom and not instance.is_uploaded:
            instance.is_uploaded = True
            instance.save(update_fields=['is_uploaded'])


# ----------------------------------------
# BLCC ViewSet (BMMU)
# ----------------------------------------
class BLCCMeetingViewSet(BaseMeetingViewSet):
    serializer_class = BLCCMeetingSerializer

    def get_queryset(self):
        master_user = self.get_master_user()
        scope = self.get_user_scope(master_user)
        role = master_user.role_id

        # ---------------- BASE QUERY ----------------
        qs = BLCC_Meeting.objects.filter(is_active=True)

        # ---------------- ROLE FILTER ----------------
        if role in [2, 3]:  # DMMU + SMMU → OVERRIDE BLOCK LOCK
            block_id = self.request.query_params.get('block')
            if block_id:
                qs = qs.filter(block_id=block_id)

            district_id = self.request.query_params.get('district')
            if district_id:
                qs = qs.filter(district_id=district_id)

        else:
            # BMMU → STRICT LOCK
            if not scope.block_id:
                raise PermissionDenied("User is not mapped to a specific block.")
            qs = qs.filter(block_id=scope.block_id)

        # ---------------- DATE FILTERS ----------------
        meeting_month = self.request.query_params.get('meeting_month')
        if meeting_month:
            parts = meeting_month.split('-')
            if len(parts) == 2:
                qs = qs.filter(
                    meeting_date__year=parts[0],
                    meeting_date__month=parts[1]
                )

        meeting_year = self.request.query_params.get('meeting_year')
        if meeting_year:
            qs = qs.filter(meeting_date__year=meeting_year)

        meeting_date = self.request.query_params.get('meeting_date')
        if meeting_date:
            qs = qs.filter(meeting_date=meeting_date)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        master_user = self.get_master_user()
        scope = self.get_user_scope(master_user)

        is_uploaded = True if self.request.FILES.get('mom') else False
        
        serializer.save(
            created_by=master_user,
            district_id=scope.district_id, # Inherit district from block mapping
            block_id=scope.block_id,
            is_uploaded=is_uploaded
        )

    def perform_update(self, serializer):
        master_user = self.get_master_user()
        instance = serializer.save(updated_by=master_user, updated_at=timezone.now())
        
        if instance.mom and not instance.is_uploaded:
            instance.is_uploaded = True
            instance.save(update_fields=['is_uploaded'])