from rest_framework import serializers
from TMS.models import LearningMaterial

class LearningMaterialSerializer(serializers.ModelSerializer):
    theme_name = serializers.CharField(source='theme.theme_name', read_only=True)
    training_plan_name = serializers.CharField(source='training_plan.training_name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = LearningMaterial
        fields = [
            'id', 'TH_urid', 'title', 'description', 'file', 
            'theme', 'theme_name', 
            'training_plan', 'training_plan_name', 
            'is_active', 'created_at', 'created_by_name'
        ]
        read_only_fields = ['TH_urid', 'is_active', 'created_at', 'created_by_name']