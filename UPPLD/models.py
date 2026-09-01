from django.db import models

class AspirationalBlockAchievement(models.Model):
    # Time Categorization
    year = models.CharField(max_length=10, help_text="Financial Year (e.g., 2026-27)")
    month = models.IntegerField(help_text="Month Code (1-12)")
    
    # Location Hierarchy
    div_code = models.CharField(max_length=10, default="00")
    dist_code = models.CharField(max_length=10)
    block_code = models.CharField(max_length=10)
    
    # Indicator Codes (This handles BOTH 0511 and 0512)
    prog_code = models.CharField(max_length=10, help_text="Indicator Code (0511 or 0512)")
    prog_head_code = models.CharField(max_length=10)
    
    # Payload Metrics
    unit = models.CharField(max_length=50, help_text="Number or Percentage")
    period_name_id = models.CharField(max_length=10)
    lead_dept_name_id = models.CharField(max_length=10)
    
    # Achievement Values
    mon_ach_numerator = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    mon_ach_denominator = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    mon_ach = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    cum_ach = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    
    # Temporal Strings & Disclaimer
    quarter_month = models.CharField(max_length=50, blank=True, null=True)
    six_monthly = models.CharField(max_length=50, blank=True, null=True)
    four_month = models.CharField(max_length=50, blank=True, null=True)
    disclaimer = models.TextField(blank=True, null=True)
    
    # Audit Logs
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Prevents duplicate entries. Pushing data again will just UPDATE the existing row.
        unique_together = ('year', 'month', 'dist_code', 'block_code', 'prog_code')
        ordering = ['-year', '-month', 'dist_code', 'block_code']

    def __str__(self):
        return f"{self.prog_code} | Block: {self.block_code} | {self.month}/{self.year} | Achieved: {self.cum_ach}"