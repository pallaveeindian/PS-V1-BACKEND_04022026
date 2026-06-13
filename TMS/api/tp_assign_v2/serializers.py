# serializers.py
from rest_framework import serializers
from TMS.models import TrainingPartner

class TrainingPartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingPartner
        # Including 'all' fields as requested, or you can specify exact fields
        fields = [
            'id', 
            'name', 
            'email', 
            'address', 
            'tp_short_name', 
            'tpm_registration_no',
            'master_user'
        ]