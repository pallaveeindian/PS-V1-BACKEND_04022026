from rest_framework import serializers


class DistrictMOUAnalyticsSerializer(serializers.Serializer):
    district_id = serializers.IntegerField()
    district_name_en = serializers.CharField()
    mou_target = serializers.IntegerField()
    achieved_mou = serializers.IntegerField()
    achievement_percentage = serializers.DecimalField(
        max_digits=6,
        decimal_places=1
    )
    financial_year = serializers.CharField(allow_null=True)