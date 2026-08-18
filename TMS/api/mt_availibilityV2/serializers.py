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

class ReplaceBatchMasterTrainerSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField(
        required=True, 
        help_text="ID of the Batch where the trainer is being replaced."
    )
    master_trainer_id = serializers.IntegerField(
        required=True, 
        help_text="ID of the NEW Master Trainer to be assigned."
    )        