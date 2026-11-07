# serializers.py
from rest_framework import serializers
from TMS.models import BatchHistory


class BatchHistoryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchHistory
        fields = ("batch", "status", "remarks", "created_by")