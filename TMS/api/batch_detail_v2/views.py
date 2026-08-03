from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from TMS.models import Batch
from TMS.api.batch_detail_v2.serializers import ComprehensiveBatchDetailSerializer # update import path if needed

class ComprehensiveBatchDetailView(generics.RetrieveAPIView):
    """
    Retrieves ALL details for a single Batch including plans, partners, centres,
    participants, daily attendance, cost breakdowns, media, ekyc, and schedules.
    Also dynamically groups participants block-wise into combined_batch_details.
    """
    serializer_class = ComprehensiveBatchDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        return Batch.objects.select_related(
            # Single-object forward relations
            'training_plan',
            'training_plan__theme',
            'district',
            'block',
            'partner',
            'centre',
            'batch_costing',
            'batch_closing'
        ).prefetch_related(
            # Multi-object backward relations
            'schedules',
            'ekyc_verifications',
            'attendances__participant_records',
            'batch_pictures',
            'batch_certificates',
            'participant_costs',
            
            # Centre-related nested relations
            'centre__rooms',
            'centre__tpcptocentre_set__contact_person',
            
            # Block coverages tracking
            'block_coverages__block',
            
            # Participant mappings with nested profiles, attendance summaries, and blocks for grouping
            'beneficiary_participations__beneficiary__block',
            'beneficiary_participations__attendance_summary',
            'trainer_participations__trainer__block',
            'trainer_participations__attendance_summary',
            'staff_participations__staff__block',    
            'staff_participations__attendance_summary',
            'master_trainer_participations__master_trainer'
        )