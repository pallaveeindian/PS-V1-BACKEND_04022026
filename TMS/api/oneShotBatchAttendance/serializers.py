from rest_framework import serializers

class ParticipantAttendanceRecordSerializer(serializers.Serializer):
    participant_id = serializers.CharField(max_length=255, required=True)
    participant_role = serializers.ChoiceField(choices=[('trainer', 'Trainer'), ('trainee', 'Trainee')], required=True)
    participant_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    present = serializers.BooleanField(default=False)

class OneShotBatchAttendanceSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField(required=True)
    date = serializers.DateField(required=True)
    missing_dates = serializers.ListField(
        child=serializers.DateField(), required=False, default=list
    )
    participant_records = ParticipantAttendanceRecordSerializer(many=True, required=True)