from rest_framework import serializers


class SystemHealthSerializer(serializers.Serializer):
  services = serializers.DictField()
  resources = serializers.DictField()
  database_size = serializers.CharField()
  network_telemetry = serializers.DictField()
  security_monitoring = serializers.DictField()