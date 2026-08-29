from rest_framework import serializers

class PortalSummaryReportQuerySerializer(serializers.Serializer):
    financial_year = serializers.CharField(
        required=True, 
        error_messages={"required": "financial_year query parameter is strictly required for this report."}
    )