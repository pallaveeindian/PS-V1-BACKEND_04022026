# TMS/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.permissions import AllowAny

from TMS.api import tms_views, dashboard_views, report_views

# Custom TR deletion endpoint for DMMU with strict access control and cascade handling
from TMS.api.tr_delete import TrainingRequestCustomDeleteView
from TMS.api.user_mgmnt import *

# Custom TP target assignment API
from TMS.api.tp_assign_v2.views import *

# Dashboard APIs
from TMS.api.TPHomepageV2.views import *
from TMS.api.AdminHomepage_v2.views import *
from TMS.api.PortalSummaryV2.views import *

# New Staff TR Creation APIs
from TMS.api.StaffList.views import *

# MD Maam Dashboard endpoints
from TMS.api.MD_maam_apis.views import *

# Learning Material Module APIs
from TMS.api.learning_mat_apis.views import *

# NEW TC MODULE APIs
from TMS.api.tc_module_apis.trainees_list import *
from TMS.api.tc_module_apis.batch_creator_v2 import *
from TMS.api.tc_module_apis.tp_user_mgmnt import *
from TMS.api.batch_detail_v2.views import *
from TMS.api.tc_module_apis.batch_review import *
from TMS.api.tc_module_apis.tpcp_creator_v2 import *
from TMS.api.tc_module_apis.target_ach_v2 import *
from TMS.api.tc_module_apis.tr_participants import *
from TMS.api.mt_apis_v2.views import *
from TMS.api.mt_availibilityV2.views import *

router = DefaultRouter()

# Masters
router.register(
    r"training-themes",
    tms_views.TrainingThemeViewSet,
    basename="tms-training-theme",
)
router.register(
    r"training-plans",
    tms_views.TrainingPlanViewSet,
    basename="tms-training-plan",
)
router.register(
    r"master-trainers",
    tms_views.MasterTrainerViewSet,
    basename="tms-master-trainer",
)
router.register(
    r"master-trainer-certificates",
    tms_views.MasterTrainerCertificateViewSet,
    basename="tms-master-trainer-certificate",
)

# Training partners & centres
router.register(
    r"training-partners",
    tms_views.TrainingPartnerViewSet,
    basename="tms-training-partner",
)
router.register(
    r"training-partner-banks",
    tms_views.TrainingPartnerBankViewSet,
    basename="tms-training-partner-bank",
)
router.register(
    r"training-partner-contact-persons",
    tms_views.TrainingPartnerCPViewSet,
    basename="tms-training-partner-cp",
)
router.register(
    r"training-partner-centres",
    tms_views.TrainingPartnerCentreViewSet,
    basename="tms-training-partner-centre",
)
router.register(
    r"training-partner-centre-rooms",
    tms_views.TrainingPartnerCentreRoomsViewSet,
    basename="tms-training-partner-centre-room",
)
router.register(
    r"tpcp-centre-links",
    tms_views.TPCPToCentreViewSet,
    basename="tms-tpcp-centre",
)
router.register(
    r"training-partner-submissions",
    tms_views.TrainingPartnerSubmissionViewSet,
    basename="tms-training-partner-submission",
)
router.register(
    r"training-partner-targets",
    tms_views.TrainingPartnerTargetsViewSet,
    basename="tms-training-partner-target",
)

# Targets / Authority
router.register(
    r"trp-user-scopes",
    tms_views.TRPUserScopeViewSet,
    basename="tms-trp-user-scope",
)

# Requests, batches & attendance
router.register(
    r"training-requests",
    tms_views.TrainingRequestViewSet,
    basename="tms-training-request",
)
router.register(
    r"training-request-beneficiaries",
    tms_views.TRBeneficiaryViewSet,
    basename="tms-tr-beneficiary",
)
router.register(
    r"training-request-trainers",
    tms_views.TRTrainerViewSet,
    basename="tms-tr-trainer",
)
router.register(
    r"training-request-staff",
    tms_views.TRStaffViewSet,
    basename="tms-tr-staff",
)
router.register(
    r"batches",
    tms_views.BatchViewSet,
    basename="tms-batch",
)
router.register(
    r"batch-schedules",
    tms_views.BatchScheduleViewSet,
    basename="tms-batch-schedule",
)
router.register(
    r"batch-master-trainers",
    tms_views.BatchMasterTrainerViewSet,
    basename="tms-batch-master-trainer",
)
router.register(
    r"batch-beneficiaries",
    tms_views.BatchBeneficiaryViewSet,
    basename="tms-batch-beneficiary",
)
router.register(
    r"batch-trainers",
    tms_views.BatchTrainerViewSet,
    basename="tms-batch-trainer",
)
router.register(
    r"batch-ekyc",
    tms_views.BatchEkycVerificationViewSet,
    basename="tms-batch-ekyc",
)
router.register(
    r"batch-attendance",
    tms_views.BatchAttendanceViewSet,
    basename="tms-batch-attendance",
)
router.register(
    r"participant-attendance",
    tms_views.ParticipantAttendanceViewSet,
    basename="tms-participant-attendance",
)

# Closure & certificates
router.register(
    r"tp-batch-cost-breakups",
    tms_views.TPBatchCostBreakupViewSet,
    basename="tms-tp-batch-cost-breakup",
)
router.register(
    r"batch-costs",
    tms_views.BatchCostViewSet,
    basename="tms-batch-cost",
)
router.register(
    r"batch-media",
    tms_views.BatchMediaViewSet,
    basename="tms-batch-media",
)
router.register(
    r"batch-closure-requests",
    tms_views.BatchClosureRequestViewSet,
    basename="tms-batch-closure-request",
)
router.register(
    r"batch-participant-certificates",
    tms_views.BatchParticipantCertificateViewSet,
    basename="tms-batch-participant-certificate",
)
router.register(
    r"batch-reports",
    tms_views.BatchReportViewSet,
    basename="tms-batch-report",
)

# Training Request List with filters
router.register(
    r'training-requests-list',
    tms_views.TrainingRequestListViewSet,
    basename='training-request-list'
)

urlpatterns = [
    # CRUD / core APIs
    path("", include(router.urls)),

    # TP CP to Centre Details with list API
    path(
        "tpcp_to_centre/details/",
        tms_views.TPCPCentreDetailViewSet.as_view({'get': 'list'}),
    ),

    # BMMU
    path("bmmu/dashboard/", dashboard_views.BmmuDashboardAPIView.as_view()),
    path("bmmu/trainings-list/", dashboard_views.BmmuTrainingsListAPIView.as_view()),
    path("bmmu/requests/<int:request_id>/", dashboard_views.BmmuRequestDetailAPIView.as_view()),
    path("bmmu/batches/<int:batch_id>/", dashboard_views.BmmuBatchViewAPIView.as_view()),
    path(
        "bmmu/batches/<int:batch_id>/attendance-by-date/",
        dashboard_views.BmmuBatchAttendanceDateAPIView.as_view(),
    ),

    # SMMU
    path("smmu/dashboard/", dashboard_views.SmmuDashboardAPIView.as_view()),
    path("smmu/requests/", dashboard_views.SmmuTrainingRequestsAPIView.as_view()),
    path("smmu/requests/<int:batch_id>/", dashboard_views.SmmuRequestDetailAPIView.as_view()),
    path("smmu/partner-targets/", dashboard_views.SmmuCreatePartnerTargetAPIView.as_view()),

    # DMMU
    path("dmmu/dashboard/", dashboard_views.DmmuDashboardAPIView.as_view()),
    path("dmmu/requests/", dashboard_views.DmmuTrainingRequestsAPIView.as_view()),
    path("dmmu/requests/<int:request_id>/", dashboard_views.DmmuRequestDetailAPIView.as_view()),
    path("dmmu/batches/<int:batch_id>/detail/", dashboard_views.DmmuBatchDetailAPIView.as_view()),
    path(
        "dmmu/batches/<int:batch_id>/attendance-by-date/",
        dashboard_views.DmmuBatchAttendanceDateAPIView.as_view(),
    ),
    
    # Training Report
    path('training-report/<int:id>/', tms_views.TrainingReportView.as_view(), name='training-report'),
        
    # Batches List
    path('batches-list/', tms_views.BatchesListView.as_view(), name='batches-list'),
    
    # Training Participant Report
    path(
        "cmp-training-report/",
        report_views.TmsTrainingReportViewSet.as_view({"get": "list"}),
        name="participant-training-report",
    ),
    
    path(
        "submissions/<int:pk>/download/",
        tms_views.download_submission,
        name="download_submission",
    ),    

    path(
        "preview_submission/<int:pk>/",
        tms_views.preview_submission,
        name="preview_submission",
    ),       

    # Check if participants are engaged in ongoing trainings (bulk API for TP onboarding)
    path(
        "check-training-engagement/",
        tms_views.BulkTrainingEngagementCheckAPI.as_view(),
        name="bulk-check-training-engagement"
    ),

    # To get list of deleted participants for a training request (for audit trail and data integrity purposes)
    path(
            'training-requests/<int:tr_id>/deleted-participants/', 
            tms_views.DeletedParticipantsView.as_view(), 
            name='tr-deleted-participants'
        ),

    # To change password of user on First login
    path(
        'first-login/password-verify/', 
        tms_views.TMSFirstLoginVerifyOldPasswordView.as_view(), 
        name='tms-first-login-verify-password'
    ),    
    path(
        'first-login/change-password/', 
        tms_views.TMSFirstLoginPasswordChangeView.as_view(), 
        name='tms-first-login-change-password'
    ),

    # SMMU TP Targets bulk upload
    path('tp-targets/bulk-upload/', tms_views.BulkAssignTargetsAPIView.as_view(), name='bulk-upload-targets'),   

    # Custom TR deletion endpoint for DMMU with strict access control and cascade handling
    path(
        'training-request/delete/<int:request_id>/', 
        TrainingRequestCustomDeleteView.as_view(), 
        name='custom-oneshot-training-delete'
    ),

    # User management APIs
    path(
        "manage-user/",
        ManageUserView.as_view(),
        name="manage-user"
    ),    
    path('dmmu-users/', DMMUDistrictListingView.as_view(), name='dmmu-district-users'),
    path('bmmu-users/', BMMUUserListingView.as_view(), name='bmmu-users'),

    # TMS V2 APIs,
    # New TP Assignment based on TR Financial Year
    path(
        'tp/by-target/', 
        TargetedTrainingPartnerAPIView.as_view(), 
        name='training-partners-by-target'
    ),
    # TC Module APIS,
    path(
        'batch-creator/trainees/',
        FetchTraineesForTrainingPartnerView.as_view(),
        name='selected-trainees-by-bmmu'
    ),
    path(
        'dtp/parent-partner/',
        tms_views.DTPUserPartnerResolveView.as_view(),
        name='dtp-parent-partner'
    ),
    path('batch-creator/create/', CreateOneShotBatchAPIView.as_view(), name='batch-oneshot-create'),
    path('batch-creator/update/<int:batch_id>/', OneShotUpdateBatchAPIView.as_view(), name='batch-oneshot-update'),
    path('batch-creator/delete/<int:batch_id>/', OneShotDeleteBatchAPIView.as_view(), name='batch-oneshot-delete'),

    # TP User Management APIs

    # 1) List users (Use ?type=dtp or ?type=tpcp)
    path('tp/user-management/', UserManagementAPIView.as_view(), name='user-manage-list'),
    
    # 2, 3, 4) Detail, Update, Delete a specific user
    path('tp/user-management/<int:user_id>/', UserManagementAPIView.as_view(), name='user-manage-detail'),
    
    # 5) Reset Password
    path('tp/user-management/<int:user_id>/reset-password/', UserPasswordResetAPIView.as_view(), name='user-manage-reset-pwd'),   

    # NEW Batch Detail API (Comprehensive)
    path(
        'batches/comprehensive-detail/<int:id>/', 
        ComprehensiveBatchDetailView.as_view(), 
        name='comprehensive-batch-detail'
    ),

    # Batch Reivew API
    path('batch/<int:batch_id>/approve-reject/', ApproveRejectBatchAPIView.as_view(), name='batch-approve-reject'),

    # TPCP Creator V2 API
    path('tpcp/create-oneshot/', TPCPCreateOneShotView.as_view(), name='tpcp-create-oneshot'),

    # DTP Target fetch
    path('dtp/target-count/', DTPTargetCountAPIView.as_view(), name='dtp-target-count'),

    # Batch wise TR Participant breakage
    path('tr/<int:tr_id>/participants/', TrainingRequestParticipantsAPIView.as_view(), name='tr-participants-with-batches'),

    # Public TMS Themes
    path(
        "public/training-themes/",
        tms_views.TrainingThemeViewSet.as_view(
            {"get": "list"},
            permission_classes=[AllowAny],
        ),
        name="public-training-theme-list",
    ),

    # Public TMS Training Plans
    path(
        "public/training-plans/",
        tms_views.TrainingPlanViewSet.as_view(
            {"get": "list"},
            permission_classes=[AllowAny],
        ),
        name="public-training-plan-list",
    ), 

    # Master Trainer V2 Endpoints
    path('mt-list/', MasterTrainerListAPIView.as_view(), name='master-trainer-list'),
    path('mt-detail/<int:pk>/', MasterTrainerDetailAPIView.as_view(), name='master-trainer-detail'),
    path('mt-create/', MasterTrainerCreateAPIView.as_view(), name='master-trainer-create'),
    path('mt/<int:pk>/update/', MasterTrainerUpdateAPIView.as_view(), name='master-trainer-update'),
    path('mt/<int:pk>/delete/', MasterTrainerDeleteAPIView.as_view(), name='master-trainer-delete'),
    path('master-trainer-status/list/', MasterTrainerProfileStatusListAPIView.as_view(), name='mt_profile_status_list'),
    path('master-trainer-status/verify/', MasterTrainerProfileVerifyAPIView.as_view(), name='mt_profile_status_verify'),    

    # Bulk Certificate Endpoints
    path('mt/<int:pk>/certificates/upload/', CertificateBulkUploadAPIView.as_view(), name='master-trainer-cert-upload'),
    path('mt/<int:trainer_id>/certificates/<int:cert_id>/delete/', CertificateDeleteAPIView.as_view(), name='master-trainer-cert-delete'),    

    # Master Trainer Status Check
    path('mt/<int:trainer_id>/availability/', CheckTrainerAvailabilityView.as_view(), name='check_trainer_availability'),

    # Master Trainer Replacement
    path('batch/replace-master-trainer/', ReplaceBatchMasterTrainerAPIView.as_view(), name='batch_replace_master_trainer'),

    # TP Dashboard Metrics
    path('tp/dashboard-metrics/', TrainingPartnerDashboardView.as_view(), name='tms-partner-dashboard-metrics'),

    # Staff TR Creation APIs
    path('staff/filter-options/', StaffFilterOptionsAPIView.as_view(), name='staff-filter-options'),
    path('staff/', StaffListAPIView.as_view(), name='staff-list'),
    path('staff/<str:employee_id>/', StaffDetailAPIView.as_view(), name='staff-detail'),

    # Batch Reschedule View
    path('batch/<int:batch_id>/reschedule/', tms_views.BatchRescheduleAPIView.as_view(), name='batch-reschedule'),
    path('tr-participants/bulk-remove/', tms_views.BulkRemoveTRParticipantsAPIView.as_view(), name='bulk_remove_tr_participants'),    

    # MD Maam apis
    path('reports/master-progress/', MasterProgressReportView.as_view(), name='master_progress_report'),
    path('reports/centre-summary/', TrainingCentreSummaryView.as_view(), name='centre_summary'),
    path('reports/centre-submissions/<int:centre_id>/', CentreSubmissionListView.as_view(), name='centre_submissions'),    
    path('reports/certificate-pendency/', DmmuCertificatePendencyView.as_view(), name='certificate_pendency_report'),
    path('reports/beneficiary-eligibility/', BeneficiaryEligibilityAnalyticsView.as_view(), name='beneficiary_eligibility_report'),
    path('reports/global-dashboard-stats/', HomeDashboardGlobalStatsView.as_view(), name='global_dashboard_stats'),    

    # Learning Material APIs
    path('learning-materials/', LearningMaterialListCreateAPIView.as_view(), name='learning_material_list_create'),
    path('learning-materials/<int:pk>/', LearningMaterialDetailAPIView.as_view(), name='learning_material_detail'),    

    # NEW Admin Dashboard API
    path(
        'admin/dashboard-metrics/', 
        AdminDashboardMetricsAPIView.as_view(), 
        name='admin_dashboard_metrics'
    ),
    path(
        'reports/portal-summary/', 
        PortalSummaryReportAPIView.as_view(), 
        name='portal_summary_report'
    ),    
]