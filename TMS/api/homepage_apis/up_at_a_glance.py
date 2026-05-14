from django.db.models import Count, Q, F
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.views import APIView
from rest_framework.response import Response

# Import Global/Core Models
from core.models import (
    MasterRoles, MasterUser, MasterMandal, MasterDistrictCategory,
    MasterDistrict, MasterBlock, MasterPanchayat, MasterVillage
)

# Import TMS Models
from TMS.models import (
    MasterTrainer, MasterTrainerCertificate, TrainingTheme, 
    TrainingPlan, TrainingPartner, TrainingPartnerCentre, 
    Batch, BatchBeneficiary, BatchTrainer, BatchEkycVerification
)

class UPAtAGlanceView(APIView):
    """
    Consolidated Public API for Global and Platform-specific Homepage Overview.
    Cached for 1 minute to handle high traffic instantly.
    """

    @method_decorator(cache_page(60 * 1))
    def get(self, request, *args, **kwargs):
        
        # =========================================================
        # 1. GLOBAL OVERVIEW (Users & Geography)
        # =========================================================
        
        # --- Global User Stats ---
        total_roles = MasterRoles.objects.count()
        total_users = MasterUser.objects.count()
        active_users = MasterUser.objects.filter(is_active=1).count()
        
        # Fast SQL GROUP BY for role breakdown
        role_breakdown = list(MasterUser.objects.exclude(role__isnull=True).values(
            role_name=F('role__name')
        ).annotate(
            user_count=Count('id')
        ).order_by('-user_count'))

        # --- Global Geographic Stats ---
        geo_stats = {
            "total_mandals": MasterMandal.objects.count(),
            "total_district_categories": MasterDistrictCategory.objects.count(),
            "total_districts": MasterDistrict.objects.count(),
            "total_blocks": MasterBlock.objects.count(),
            "total_panchayats": MasterPanchayat.objects.count(),
            "total_villages": MasterVillage.objects.count(),
        }

        # =========================================================
        # 2. TMS ANALYTICS (Fully Operational)
        # =========================================================
        
        # --- Trainer Stats ---
        trainer_data = MasterTrainer.objects.aggregate(
            total_trainers=Count('id'),
            brp_count=Count('id', filter=Q(designation='BRP')),
            drp_count=Count('id', filter=Q(designation='DRP')),
            srp_count=Count('id', filter=Q(designation='SRP')),
            with_certificates=Count('certificates__trainer', distinct=True)
        )

        # --- Theme & Plan Stats ---
        total_themes = TrainingTheme.objects.count()
        total_plans = TrainingPlan.objects.count()
        plans_per_theme = list(TrainingTheme.objects.annotate(
            plan_count=Count('THEME')
        ).values('theme_name', 'plan_count'))

        # --- Partner & Centre Stats ---
        partner_data = TrainingPartner.objects.aggregate(total_partners=Count('id'))
        total_centres = TrainingPartnerCentre.objects.count()
        centres_per_partner = list(TrainingPartner.objects.annotate(
            centre_count=Count('centres')
        ).values('name', 'tp_short_name', 'centre_count'))

        # --- Batch Status Stats ---
        batch_stats = Batch.objects.aggregate(
            total_batches=Count('id'),
            ongoing=Count('id', filter=Q(status='ONGOING')),
            completed=Count('id', filter=Q(status='COMPLETED')),
            scheduled=Count('id', filter=Q(status='SCHEDULED')),
            pending=Count('id', filter=Q(status='PENDING')),
            rejected=Count('id', filter=Q(status='REJECTED')),
            under_review=Count('id', filter=Q(status='REVIEW'))
        )

        # --- Participation & Verification Stats ---
        participation_stats = {
            "beneficiaries_involved": BatchBeneficiary.objects.count(),
            "trainers_involved": BatchTrainer.objects.count(),
            "ekyc_verified_trainees": BatchEkycVerification.objects.filter(
                participant_role='trainee', ekyc_status='VERIFIED'
            ).count(),
            "ekyc_verified_trainers": BatchEkycVerification.objects.filter(
                participant_role='trainer', ekyc_status='VERIFIED'
            ).count(),
        }

        # =========================================================
        # FINAL CONSOLIDATED PAYLOAD
        # =========================================================
        return Response({
            "status": "success",
            
            # --- NEW: Global System Overview ---
            "global_overview": {
                "users": {
                    "total_roles_available": total_roles,
                    "total_registered_users": total_users,
                    "total_active_users": active_users,
                    "role_breakdown": role_breakdown
                },
                "geography": geo_stats
            },

            # --- Platform Specific Overviews ---
            "platform_overview": {
                # Placeholder for epSakhi (EPSMS)
                "epSakhi": {
                    "platform_name": "Udhyam Sakhi App",
                    "status": "Operational",
                    "metrics": {
                        "total_entrepreneurs": 0,
                        "crp_verified": 0,
                        "enterprises_tracked": 0
                    }
                },
                # Placeholder for LDMS
                "LDMS": {
                    "platform_name": "Lakhpati Didi Management System (LDMS)",
                    "status": "Coming Soon",
                    "metrics": {
                        "total_didis": 0,
                        "survey_completed": 0,
                        "income_enhanced": 0
                    }
                },
                # Detailed TMS Analytics
                "TMS": {
                    "platform_name": "Training Management System (TMS)",
                    "status": "Operational",
                    "trainers": {
                        "total": trainer_data['total_trainers'],
                        "bifurcation": {
                            "BRP": trainer_data['brp_count'],
                            "DRP": trainer_data['drp_count'],
                            "SRP": trainer_data['srp_count']
                        },
                        "certified_trainers": trainer_data['with_certificates']
                    },
                    "training_partners": {
                        "total_partners": partner_data['total_partners'],
                        "total_centres": total_centres,
                        "centres_breakdown": centres_per_partner
                    },
                    "curriculum": {
                        "total_themes": total_themes,
                        "total_plans": total_plans,
                        "plans_breakdown": plans_per_theme
                    },
                    "batches": batch_stats,
                    "participation_and_verification": participation_stats
                }
            }
        })