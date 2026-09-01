from rest_framework import serializers
from .models import AspirationalBlockAchievement

class AspirationalBlockAchievementSerializer(serializers.ModelSerializer):
    # Mapping the exact JSON keys from the Planning Dept API to our Django Model fields
    Block_code = serializers.CharField(source='block_code')
    ProgHeadCode = serializers.CharField(source='prog_head_code')
    PeriodNameId = serializers.CharField(source='period_name_id')
    LeadDeptNameId = serializers.CharField(source='lead_dept_name_id')
    mon_ach_numirator = serializers.DecimalField(source='mon_ach_numerator', max_digits=18, decimal_places=2)
    QuarterMonth = serializers.CharField(source='quarter_month', allow_blank=True, required=False)
    SixMonthly = serializers.CharField(source='six_monthly', allow_blank=True, required=False)
    FourMonth = serializers.CharField(source='four_month', allow_blank=True, required=False)
    Disclaimer = serializers.CharField(source='disclaimer', allow_blank=True, required=False)

    class Meta:
        model = AspirationalBlockAchievement
        fields = [
            'year', 'month', 'div_code', 'dist_code', 'Block_code', 
            'prog_code', 'ProgHeadCode', 'unit', 'PeriodNameId', 
            'LeadDeptNameId', 'mon_ach_numirator', 'mon_ach_denominator', 
            'mon_ach', 'cum_ach', 'QuarterMonth', 'SixMonthly', 
            'FourMonth', 'Disclaimer'
        ]