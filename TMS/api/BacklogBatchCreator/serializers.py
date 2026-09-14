from rest_framework import serializers

class BacklogBatchOneShotSerializer(serializers.Serializer):
    batch_info = serializers.DictField(required=True)
    master_trainers = serializers.ListField(required=False, default=list)
    participants = serializers.ListField(required=True)
    blocks_coverage = serializers.ListField(required=False, default=list)
    schedules = serializers.ListField(required=False, default=list)
    ekyc_verifications = serializers.ListField(required=False, default=list)
    attendances = serializers.ListField(required=False, default=list)
    participant_costs = serializers.ListField(required=False, default=list)
    batch_cost = serializers.DictField(required=False, default=dict)
    closure_request = serializers.DictField(required=False, default=dict)