from rest_framework import serializers

class RecalculateAttendanceSerializer(serializers.Serializer):
    """
    Validates the POST request. Accepts an optional batch_id.
    """
    batch_id = serializers.IntegerField(required=False, allow_null=True)