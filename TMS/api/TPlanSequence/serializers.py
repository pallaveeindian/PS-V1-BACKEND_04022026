from rest_framework import serializers
from TMS.models import TrainingPlanSequence, TrainingPlan

class TrainingPlanSequenceReportSerializer(serializers.Serializer):
    sr_no = serializers.IntegerField()
    plan_id = serializers.IntegerField(source="training_plan.id")
    plan_name = serializers.CharField(source="training_plan.training_name")
    theme_name = serializers.CharField(source="training_plan.theme.theme_name", allow_null=True)
    sequence_group_name = serializers.CharField()
    step_order = serializers.IntegerField()
    target = serializers.IntegerField()
    onboarded = serializers.IntegerField()
    descended_entries = serializers.IntegerField()
    successful_descendants = serializers.IntegerField()
    dropout_descendants = serializers.IntegerField()
    lateral_entries = serializers.IntegerField()

class TrainingPlanSequenceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingPlanSequence
        fields = [
            'sequence_group_name', 
            'training_plan', 
            'step_order', 
            'next_training_plan'
        ]

    def validate(self, attrs):
        # Support partial updates by falling back to the existing instance values if not provided
        group_name = attrs.get('sequence_group_name') or (self.instance.sequence_group_name if self.instance else None)
        plan = attrs.get('training_plan') or (self.instance.training_plan if self.instance else None)

        # Prevent duplicate active entries for the same plan in the same group
        qs = TrainingPlanSequence.objects.filter(
            sequence_group_name=group_name, 
            training_plan=plan, 
            is_active=True
        )
        
        # If we are editing, exclude the current row from the uniqueness check
        if self.instance:
            qs = qs.exclude(id=self.instance.id)

        if qs.exists():
            plan_name = getattr(plan, 'training_name', 'Unknown Plan')
            raise serializers.ValidationError({
                "training_plan": f"The plan '{plan_name}' is already assigned to the sequence group '{group_name}'."
            })
            
        return attrs

class TrainingPlanSequenceListSerializer(serializers.ModelSerializer):
    current_plan_name = serializers.CharField(source='training_plan.training_name', read_only=True)
    theme_name = serializers.CharField(source='training_plan.theme.theme_name', read_only=True, default="N/A")
    
    # Custom fields for graceful fallbacks
    next_plan_name = serializers.SerializerMethodField()
    prev_plan_name = serializers.SerializerMethodField()

    class Meta:
        model = TrainingPlanSequence
        fields = [
            'id',
            'sequence_group_name',
            'step_order',
            'training_plan',
            'current_plan_name',
            'theme_name',
            'next_training_plan',
            'next_plan_name',
            'prev_plan_name',
            'is_active'
        ]

    def get_next_plan_name(self, obj):
        if obj.next_training_plan:
            return obj.next_training_plan.training_name
        return "None (Last Step)"

    def get_prev_plan_name(self, obj):
        # Fetches the value annotated by the Subquery in the View
        prev_name = getattr(obj, 'annotated_prev_plan_name', None)
        if prev_name:
            return prev_name
        return "None (First Step)"        