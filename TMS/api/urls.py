# TMS/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from TMS.api import tms_views, dashboard_views

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
    r"tr-closures",
    tms_views.TRClosureViewSet,
    basename="tms-tr-closure",
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
]
