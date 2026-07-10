from rest_framework import serializers
from .models import Ticket, TicketBody, TicketMedia

class TicketMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketMedia
        fields = ['id', 'screenshot', 'created_at']

class TicketBodySerializer(serializers.ModelSerializer):
    # These read-only fields fetch names directly from the related core models
    district_name = serializers.CharField(source='district.name', read_only=True, default="N/A")
    block_name = serializers.CharField(source='block.name', read_only=True, default="N/A")

    class Meta:
        model = TicketBody
        fields = [
            'id', 'district', 'district_name', 'block', 'block_name', 
            'username', 'problem_message', 'mobile_no'
        ]

class TicketDetailSerializer(serializers.ModelSerializer):
    # Nested serializers to provide comprehensive detail
    ticket_body = TicketBodySerializer(read_only=True)
    ticket_media = TicketMediaSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [
            'id', 'ticket_code', 'is_solved', 'pmu_response', 
            'master_user', 'ticket_body', 'ticket_media', 
            'created_at', 'updated_at', 'is_active'
        ]