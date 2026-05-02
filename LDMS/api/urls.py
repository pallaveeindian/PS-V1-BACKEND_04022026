# LDMS/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .analytics_views import *
from .ldms_views import *
from .report_views import *
from .meet_views import *

router = DefaultRouter()

# --------------------
# Department + Scheme
# --------------------

router.register(
    r"departments",
    DepartmentViewSet,
    basename="ldms-department",
)
router.register(
    r"schemes",
    SchemeViewSet, 
    basename="ldms-scheme",
)

router.register(
    r"recorded-plds",
    recordedPLDViewset,
    basename="ldms-recorded-pld",
)

router.register(
    r"sbtypes",
    SBtypeViewset,
    basename="ldms-sbtype",
)

router.register(
    r"support-buckets",
    SupportBucketViewset,
    basename="ldms-support-bucket",
)

router.register(
    r"training-supports",
    TrainingSupportViewset,
    basename="ldms-training-support",
)

router.register(
    r"bucket-approvals",
    BucketApprovalViewset,
    basename="ldms-bucket-approval",
)

router.register(
    r"reports/recorded-beneficiaries",
    RecordedBeneficiaryReportViewSet,
    basename="ldms-recorded-beneficiary-report",
)

# DLCC and BLCC Meeting URLs
router.register(r'dlcc-meetings', DLCCMeetingViewSet, basename='dlcc-meetings')
router.register(r'blcc-meetings', BLCCMeetingViewSet, basename='blcc-meetings')

urlpatterns = [
    path("", include(router.urls)),
    path(
        "map-analytics/",
        UpsrlmAnalyticsView.as_view(),
        name="map-analytics",
    ),

    # Notifications URLs
    path('notifications/', NotificationListAPIView.as_view(), name='notification-list'),
    path('notifications/<int:id>/read/', NotificationMarkReadAPIView.as_view(), name='notification-mark-read'),    

]