# TMS/api/TPHomepageV2/serializers.py
from rest_framework import serializers

class DistrictTargetAchievementSerializer(serializers.Serializer):
    district_id = serializers.IntegerField()
    district_name_en = serializers.CharField()
    assigned_targets = serializers.IntegerField()
    achieved_batches = serializers.IntegerField()

class ThemeTargetAchievementSerializer(serializers.Serializer):
    theme_name = serializers.CharField()
    assigned_targets = serializers.IntegerField()
    achieved_batches = serializers.IntegerField()

class KpiCardInfoSerializer(serializers.Serializer):
    total_batches_created = serializers.IntegerField()
    ongoing_batches = serializers.IntegerField()
    pending_batches = serializers.IntegerField()
    closed_batches = serializers.IntegerField()
    total_participants_allotted = serializers.IntegerField()
    total_participants_trained = serializers.IntegerField()

class DistrictCentreSummarySerializer(serializers.Serializer):
    district_id = serializers.IntegerField()
    district_name_en = serializers.CharField()
    registered_centres_count = serializers.IntegerField()

class DistrictTpPerformanceSerializer(serializers.Serializer):
    district_id = serializers.IntegerField()
    district_name_en = serializers.CharField()
    district_tp_username = serializers.CharField(allow_null=True)
    batches_created = serializers.IntegerField()
    batches_closed = serializers.IntegerField()
    performance_rank = serializers.IntegerField()

class TPDashboardResponseSerializer(serializers.Serializer):
    financial_year = serializers.CharField()
    training_partner_name = serializers.CharField()
    kpi_card_info = KpiCardInfoSerializer()
    theme_wise_metrics = ThemeTargetAchievementSerializer(many=True)
    district_wise_metrics = DistrictTargetAchievementSerializer(many=True)
    district_wise_centres = DistrictCentreSummarySerializer(many=True)
    district_tp_performance = DistrictTpPerformanceSerializer(many=True)