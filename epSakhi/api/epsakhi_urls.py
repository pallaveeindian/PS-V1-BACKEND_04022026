# epSakhi/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import *
from .analytics_views import *

router = DefaultRouter()
router.register('crp', CRPEPViewSet, basename='crp')
router.register('recorded-beneficiaries', BeneficiaryRecordedViewSet, basename='recorded-beneficiaries')
router.register('existing-enterprise', ExistingEnterpriseViewSet, basename='existing-enterprise')
router.register('new-enterprise', NewEnterpriseViewSet, basename='new-enterprise')
router.register('no-enterprise-forms', NoEnterpriseFormViewSet, basename='no-enterprise-forms')
router.register('no-enterprise-wages', NoEnterpriseWageViewSet, basename='no-enterprise-wages')

# child table routers
router.register(
    r'enterprise-licenses',
    EnterpriseLicensesViewSet,
    basename='enterprise-licenses'
)

router.register(
    r'enterprise-loan-details',
    EnterpriseLoanDetailViewSet,
    basename='enterprise-loan-details'
)

router.register(
    r'enterprise-subsidy-details',
    EnterpriseSubsidyDetailViewSet,
    basename='enterprise-subsidy-details'
)

router.register(
    r'enterprise-shop',
    EnterpriseShopViewSet,
    basename='enterprise-shop'
)

router.register(
    r'shop-media',
    ShopMediaViewSet,
    basename='shop-media'
)

router.register(
    r'enterprise-products',
    EnterpriseProductViewSet,
    basename='enterprise-products'
)

router.register(
    r'product-media',
    ProductMediaViewSet,
    basename='product-media'
)

router.register(
    r'enterprise-media',
    EnterpriseMediaViewSet,
    basename='enterprise-media'
)

# Shared tables (enterprise_id = TH_urid, existing + new)
router.register(
    r'enterprise-types',
    EnterpriseTypeCategoryViewSet,
    basename='enterprise-types'
)

router.register(
    r'enterprise-support',
    EnterpriseSupportViewSet,
    basename='enterprise-support'
)

router.register(
    r'mandatory-fund',
    EnterpriseMandatoryFundViewSet,
    basename='mandatory-fund'
)

router.register(
    r'enterprise-training-reqs',
    EnterpriseTrainingReqViewSet,
    basename='enterprise-training-reqs'
)

router.register(
    r'training-certificates',
    TrainingCertificatesViewSet,
    basename='training-certificates'
)

router.register(
    r"crud-panchayats-under-crp",
    CRPPanchayatViewSet,
    basename="crp-panchayat"
)

# CRP-Panchayat mapping Form Views
router.register(
    r'crp-panchayat-bulk',
    CRPPanchayatBulkViewSet,
    basename='crp-panchayat-bulk'
)


mapping_urls = [
    path(
        'crp/<int:pk>/link-panchayats/',
        CRPPanchayatMappingViewSet.as_view({'post': 'link'}),
        name='crp-link-panchayats',
    ),
]

custom_urls = [
    # CRP helper APIs
    path('crp-list/<str:clf_code>/', CRPListByClfView.as_view(), name='crp-list-by-clf'),
    path('crp-detail/<str:member_code>/', CRPDetailView.as_view(), name='crp-detail-by-member'),
    path('crp-detail/id/<str:id>/', CRPDetailbyUserID.as_view(), name='crp-detail-by-user'),
    path(
        "panchayats-under-crp/",
        CRPPanchayatsUnderCrpView.as_view()
    ),
    path(
        'panchayats-under-crp/id/<str:id>/',
        CRPPanchayatsUnderCrpByID.as_view(),
        name='panchayats-under-crp-id',
    ),
    path(
        'panchayats-under-crp/<str:member_code>/',
        CRPPanchayatsUnderCrpView.as_view(),
        name='panchayats-under-crp',
    ),

    # epSakhi recorded-beneficiaries shortcuts
    path('epsakhi-list/<str:shg_code>/', EpsakhiListByShgView.as_view(), name='epsakhi-list'),
    path('epsakhi-detail/<str:member_code>/', EpsakhiDetailByMemberView.as_view(), name='epsakhi-detail'),
    path(
        "crp-panch-list/",
        CRPListAPIView.as_view(),
        name="crp-list",
    )
]

# Analytics
analytics_urls = [
    path('eps-admin-dash/', BeneficiaryEnterpriseAnalyticsView.as_view(), name='eps-admin-dashboard'),
    path('eps-admin-crp/', CRPBeneficiaryAnalyticsView.as_view(), name='eps-admin-crp-recorded'),
]

urlpatterns = [
    path('', include(router.urls)),
    *mapping_urls,
    *custom_urls,
    *analytics_urls,
]
