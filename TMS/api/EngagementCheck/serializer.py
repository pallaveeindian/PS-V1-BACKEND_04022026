# Desktop/BDO_Projects/pragati_setu/TMS/api/EngagementCheck/serializer.py
from rest_framework import serializers

# -------------------------------------------------------------
# Reusable Nested Serializers
# -------------------------------------------------------------
class BatchDataSerializer(serializers.Serializer):
    batch_code = serializers.CharField(allow_null=True, required=False)
    status = serializers.CharField(allow_null=True, required=False)
    start_date = serializers.DateField(allow_null=True, required=False)
    end_date = serializers.DateField(allow_null=True, required=False)
    location = serializers.CharField(allow_null=True, required=False)
    training_plan = serializers.CharField(allow_null=True, required=False)

class RequestDataSerializer(serializers.Serializer):
    request_id = serializers.IntegerField(allow_null=True, required=False)
    status = serializers.CharField(allow_null=True, required=False)
    level = serializers.CharField(allow_null=True, required=False)
    training_plan = serializers.CharField(allow_null=True, required=False)

# -------------------------------------------------------------
# Main API Response Serializers
# -------------------------------------------------------------
class TrainerStatusSerializer(serializers.Serializer):
    trainer_name = serializers.CharField()
    trainer_id = serializers.IntegerField()
    is_busy = serializers.BooleanField()
    engaged_in = serializers.CharField(allow_null=True, required=False) # 'BATCH', 'TRAINING_REQUEST', or None
    message = serializers.CharField(allow_null=True, required=False)
    
    # Nested Data
    batch_data = BatchDataSerializer(allow_null=True, required=False)
    request_data = RequestDataSerializer(allow_null=True, required=False)


class BeneficiaryStatusSerializer(serializers.Serializer):
    member_name = serializers.CharField()
    lokos_member_code = serializers.CharField()
    is_busy = serializers.BooleanField()
    engaged_in = serializers.CharField(allow_null=True, required=False) # 'BATCH', 'TRAINING_REQUEST', or None
    message = serializers.CharField(allow_null=True, required=False)
    
    # Nested Data
    batch_data = BatchDataSerializer(allow_null=True, required=False)
    request_data = RequestDataSerializer(allow_null=True, required=False)