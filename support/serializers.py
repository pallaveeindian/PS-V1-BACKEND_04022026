from rest_framework import serializers
from .models import Ticket, TicketBody, TicketMedia
from core.models import MasterDistrict, MasterBlock

class TicketDistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterDistrict
        fields = ['district_id', 'district_name_en', 'district_short_name_en']

class TicketBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterBlock
        fields = ['block_id', 'block_name_en', 'block_name_local', 'is_aspirational']

class TicketMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketMedia
        fields = ['id', 'screenshot', 'created_at']

class TicketBodySerializer(serializers.ModelSerializer):
    # These read-only fields fetch names directly from the related core models
    district_obj = TicketDistrictSerializer(
        source="district",
        read_only=True,
    )
    block_obj = TicketBlockSerializer(
        source="block",
        read_only=True,
    )

    class Meta:
        model = TicketBody
        fields = [
            'id', 'district', 'district_obj', 'block', 'block_obj', 
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