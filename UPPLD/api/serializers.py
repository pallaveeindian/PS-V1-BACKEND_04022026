from rest_framework import serializers
from UPPLD.models import AspirationalBlockAchievement

class AspirationalBlockAchievementListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AspirationalBlockAchievement
        fields = [
            'id',
            'year',
            'month',
            'div_code',
            'dist_code',
            'block_code',
            'prog_code',
            'prog_head_code',
            'unit',
            'period_name_id',
            'lead_dept_name_id',
            'mon_ach_numerator',
            'mon_ach_denominator',
            'mon_ach',
            'cum_ach',
            'quarter_month',
            'six_monthly',
            'four_month',
            'disclaimer',
            'created_at',
            'updated_at',
        ]