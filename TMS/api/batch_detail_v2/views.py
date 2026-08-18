from django.db.models import Prefetch, Q
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from TMS.models import *

from .serializers import *

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
        # 1. Base QuerySet - Enforce is_active=True on the Batch 
        # and safely ensure forward relations (if they exist) are also active.
        qs = Batch.objects.filter(
            Q(training_plan__isnull=True) | Q(training_plan__is_active=True),
            Q(partner__isnull=True) | Q(partner__is_active=True),
            Q(centre__isnull=True) | Q(centre__is_active=True),
            is_active=True
        ).select_related(
            # Single-object forward relations
            'training_plan',
            'training_plan__theme',
            'district',
            'block',
            'partner',
            'centre'
        )

        # 2. Prefetch Related - Strictly enforcing is_active=True on EVERY nested collection
        qs = qs.prefetch_related(
            # Reverse OneToOne Relations (Using Prefetch to safely filter soft-deletes)
            Prefetch('batch_costing', queryset=BatchCost.objects.filter(is_active=True)),
            Prefetch('batch_closing', queryset=BatchClosureRequest.objects.filter(is_active=True)),

            # Batch Metadata
            Prefetch('schedules', queryset=BatchSchedule.objects.filter(is_active=True)),
            Prefetch('ekyc_verifications', queryset=BatchEkycVerification.objects.filter(is_active=True)),
            Prefetch('batch_pictures', queryset=BatchMedia.objects.filter(is_active=True)),
            Prefetch('batch_certificates', queryset=BatchParticipantCertificate.objects.filter(is_active=True)),
            Prefetch('participant_costs', queryset=TPBatchCostBreakup.objects.filter(is_active=True)),

            # Nested Attendance Records
            Prefetch(
                'attendances',
                queryset=BatchAttendance.objects.filter(is_active=True).prefetch_related(
                    Prefetch('participant_records', queryset=ParticipantAttendance.objects.filter(is_active=True))
                )
            ),

            # Centre Details
            Prefetch('centre__rooms', queryset=TrainingPartnerCentreRooms.objects.filter(is_active=True)),
            Prefetch(
                'centre__tpcptocentre_set',
                queryset=TPCPToCentre.objects.filter(
                    is_active=True, 
                    contact_person__is_active=True
                ).select_related('contact_person')
            ),

            # Block coverages tracking
            Prefetch('block_coverages', queryset=BatchBlockCoverage.objects.filter(is_active=True).select_related('block')),
            
            # Participant mappings with nested active profiles and active attendance summaries
            Prefetch(
                'beneficiary_participations',
                queryset=BatchBeneficiary.objects.filter(
                    is_active=True,
                    beneficiary__is_active=True
                ).select_related('beneficiary__block').prefetch_related(
                    Prefetch('attendance_summary', queryset=BeneficiaryAttendanceSummary.objects.filter(is_active=True))
                )
            ),
            
            Prefetch(
                'trainer_participations',
                queryset=BatchTrainer.objects.filter(
                    is_active=True,
                    trainer__is_active=True
                ).select_related('trainer__block').prefetch_related(
                    Prefetch('attendance_summary', queryset=BeneficiaryAttendanceSummary.objects.filter(is_active=True))
                )
            ),
            
            Prefetch(
                'staff_participations',
                queryset=BatchStaff.objects.filter(
                    is_active=True,
                    staff__is_active=True
                ).select_related('staff__block').prefetch_related(
                    Prefetch('attendance_summary', queryset=BeneficiaryAttendanceSummary.objects.filter(is_active=True))
                )
            ),
            
            Prefetch(
                'master_trainer_participations',
                queryset=BatchMasterTrainer.objects.filter(
                    is_active=True,
                    master_trainer__is_active=True
                ).select_related('master_trainer')
            )
        )

        return qs