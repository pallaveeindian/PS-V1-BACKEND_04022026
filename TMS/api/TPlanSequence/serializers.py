from rest_framework import serializers
from TMS.models import TrainingPlanSequence

class TrainingPlanSequenceReportSerializer(serializers.Serializer):
    sr_no = serializers.IntegerField()
    plan_id = serializers.IntegerField(source="training_plan.id")
    plan_name = serializers.CharField(source="training_plan.training_name")
    theme_name = serializers.CharField(source="training_plan.theme.theme_name", allow_null=True)
    sequence_group_name = serializers.CharField()
    step_order = serializers.IntegerField()
    target = serializers.IntegerField()
    onboarded = serializers.IntegerField()
    descended_entries = serializers.IntegerField()
    successful_descendants = serializers.IntegerField()
    dropout_descendants = serializers.IntegerField()
    lateral_entries = serializers.IntegerField()