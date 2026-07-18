from rest_framework import serializers
from TMS.models import TrainingRequest, Batch

class AvailabilityTrainingRequestSerializer(serializers.ModelSerializer):
    """Serializer to return the full Training Request object when a trainer is busy."""
    class Meta:
        model = TrainingRequest
        fields = '__all__'

class AvailabilityBatchSerializer(serializers.ModelSerializer):
    """Serializer to return the full Batch object when a trainer is busy."""
    class Meta:
        model = Batch
        fields = '__all__'