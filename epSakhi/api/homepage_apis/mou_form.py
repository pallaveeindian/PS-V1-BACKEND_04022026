from django.db.models import OuterRef, Subquery, Value, IntegerField, CharField
from django.db.models import F, FloatField, ExpressionWrapper
from django.db.models.functions import Coalesce, Cast
from django.db.models import Case, When

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination

from core.models import MasterDistrict
from epSakhi.models import DistMOUTarget

from .serializers import DistrictMOUAnalyticsSerializer

class PublicHomepagePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 500


class PublicDistrictMOUAnalyticsAPIView(APIView):
    """
    Public Homepage Analytics
    District wise Target vs Achievement
    """

    permission_classes = [AllowAny]

    def get(self, request):

        target_qs = DistMOUTarget.objects.filter(
            district_id=OuterRef("district_id"),
            deleted_at__isnull=True
        )

        queryset = (
            MasterDistrict.objects
            .annotate(
                mou_target=Coalesce(
                    Subquery(
                        target_qs.values("mou_target")[:1]
                    ),
                    Value(0),
                    output_field=IntegerField()
                ),

                achieved_mou=Coalesce(
                    Subquery(
                        target_qs.values("achieved_mou")[:1]
                    ),
                    Value(0),
                    output_field=IntegerField()
                ),

                financial_year=Coalesce(
                    Subquery(
                        target_qs.values("financial_year")[:1]
                    ),
                    Value(""),
                    output_field=CharField()
                ),
            )
            .annotate(
                achievement_percentage=Case(
                    When(
                        mou_target=0,
                        then=Value(0.0)
                    ),
                    default=ExpressionWrapper(
                        (
                            Cast(F("achieved_mou"), FloatField()) * 100.0
                        ) / Cast(F("mou_target"), FloatField()),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                )
            )
            .values(
                "district_id",
                "district_name_en",
                "mou_target",
                "achieved_mou",
                "achievement_percentage",
                "financial_year",
            )
            .order_by(
                "-achieved_mou",
                "district_name_en"
            )
        )

        paginator = PublicHomepagePagination()

        page = paginator.paginate_queryset(
            queryset,
            request
        )

        serializer = DistrictMOUAnalyticsSerializer(
            page,
            many=True
        )

        return paginator.get_paginated_response(
            serializer.data
        )    