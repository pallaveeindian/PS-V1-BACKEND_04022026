# TMS\api\batch_reversal\serializers.py
from rest_framework import serializers


class BatchReversalSerializer(serializers.Serializer):

    batch_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        required=True
    )

    target_status = serializers.ChoiceField(
        choices=["PENDING", "REJECTED"],
        required=True
    )

    def validate_batch_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError(
                "Duplicate batch IDs are not allowed."
            )

        return value