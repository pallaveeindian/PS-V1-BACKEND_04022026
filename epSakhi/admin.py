# epSakhi/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import (
    CRPEP,
    BeneficiaryRecorded,
    ExistingEnterprise,
    NewEnterprise,
    EnterpriseLoanDetail,
    EnterpriseSubsidyDetail,
    EnterpriseTrainingReq,
    EnterpriseMedia,
    EnterpriseProduct,
    EnterpriseTypeCategory,
    NoEnterpriseForm,
    NoEnterpriseWage,
)


@admin.register(CRPEP)
class CRPEPAdmin(admin.ModelAdmin):
    """
    Admin for CRPEP model.
    Note: district_id/block_id/panchayat_id are stored as plain integer ID fields (not FKs).
    """
    list_display = (
        'id',
        'name',
        'mobile_number',
        'district_id',
        'block_id',
        'panchayat_id',
        'lokos_shg_code',
        'lokos_member_code',
        'master_user_link',
        'created_at',
    )
    search_fields = ['name', 'mobile_number', 'lokos_member_code', 'lokos_shg_code']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at', 'TH_urid']

    def master_user_link(self, obj):
        """Show linked MasterUser username if available (safe: created_by is non-managed FK)."""
        try:
            mu = obj.master_user
            if mu:
                # If admin for core.MasterUser is registered, link to it
                admin_url = reverse('admin:core_masteruser_change', args=(mu.pk,))
                return format_html('<a href="{}">{}</a>', admin_url, getattr(mu, 'username', str(mu)))
        except Exception:
            pass
        return getattr(obj, 'master_user_id', None) or '-'
    master_user_link.short_description = 'MasterUser'


@admin.register(BeneficiaryRecorded)
class BeneficiaryRecordedAdmin(admin.ModelAdmin):
    """
    Admin for recorded beneficiaries (epSakhi_recorBenefs)
    Primary key is TH_urid.
    """
    list_display = (
        'TH_urid',
        'lokos_member_code',
        'applicant_name',
        'age',
        'gender',
        'lokos_shg_code',
        'district_id',
        'block_id',
        'panchayat_id',
        'village_id',
        'enterprise_link',
        'created_at',
    )
    search_fields = ['applicant_name', 'lokos_member_code', 'mobile', 'email', 'enterprise_id']
    list_filter = ['gender', 'marital_status', 'category', 'district_id', 'block_id']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']

    def enterprise_link(self, obj):
        """
        Link to the enterprise form (Existing or New) if enterprise_id is present.
        enterprise_id stores the TH_urid of the enterprise record.
        """
        eid = getattr(obj, 'enterprise_id', None)
        if not eid:
            return '-'
        # Try to find in ExistingEnterprise first, then NewEnterprise
        try:
            ent = ExistingEnterprise.objects.filter(TH_urid=eid).first()
            model_name = 'existingenterprise'
            if not ent:
                ent = NewEnterprise.objects.filter(TH_urid=eid).first()
                model_name = 'newenterprise'
            if ent:
                # these models are in this app; build admin url
                admin_url = reverse(f'admin:epSakhi_{model_name}_change', args=(ent.TH_urid,))
                return format_html('<a href="{}">{}</a>', admin_url, f"{ent.TH_urid}")
        except Exception:
            pass
        return eid
    enterprise_link.short_description = 'Enterprise'


@admin.register(ExistingEnterprise)
class ExistingEnterpriseAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'enterprise_name',
        'recorded_benef_id_link',
        'year_of_establishment',
        'total_emp',
        'number_of_shg_emp',
        'monthly_income_estimate',
        'created_at',
    )
    search_fields = ['enterprise_name', 'recorded_benef_id']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']

    def recorded_benef_id_link(self, obj):
        try:
            rb = obj.recorded_benef_id
            if rb:
                admin_url = reverse('admin:epSakhi_beneficiaryrecorded_change', args=(rb,))
                return format_html('<a href="{}">{}</a>', admin_url, rb)
        except Exception:
            pass
        return obj.recorded_benef_id or '-'
    recorded_benef_id_link.short_description = 'RecordedBeneficiary'


@admin.register(NewEnterprise)
class NewEnterpriseAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'recorded_benef_id_link',
        'applicant_special_category',
        'has_shg_cif',
        'is_training_received',
        'is_training_required',
        'declaration_confirmed',
        'created_at',
    )
    search_fields = ['recorded_benef_id', 'applicant_special_category']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']

    def recorded_benef_id_link(self, obj):
        try:
            rb = obj.recorded_benef_id
            if rb:
                admin_url = reverse('admin:epSakhi_beneficiaryrecorded_change', args=(rb,))
                return format_html('<a href="{}">{}</a>', admin_url, rb)
        except Exception:
            pass
        return obj.recorded_benef_id or '-'
    recorded_benef_id_link.short_description = 'RecordedBeneficiary'


@admin.register(EnterpriseLoanDetail)
class EnterpriseLoanDetailAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'enterprise_id',
        'form_type',
        'institution_name',
        'loan_amount',
        'date_taken',
        'repayment_status',
        'created_at',
    )
    search_fields = ['enterprise_id', 'institution_name']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']


@admin.register(EnterpriseSubsidyDetail)
class EnterpriseSubsidyDetailAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'enterprise_id',
        'subsidy_type',
        'subsidy_name',
        'created_at',
    )
    search_fields = ['enterprise_id', 'subsidy_type', 'subsidy_name']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']


@admin.register(EnterpriseTrainingReq)
class EnterpriseTrainingReqAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'enterprise_id',
        'form_type',
        'training_module_name',
        'sector',
        'department',
        'duration',
        'created_at',
    )
    search_fields = ['enterprise_id', 'training_module_name', 'sector', 'department']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']


@admin.register(EnterpriseMedia)
class EnterpriseMediaAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'enterprise_id',
        'form_type',
        'photo_entrepreneur_present',
        'photo_enterprise_present',
        'created_at',
    )
    search_fields = ['enterprise_id']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']

    def photo_entrepreneur_present(self, obj):
        return bool(getattr(obj, 'photo_entrepreneur'))
    photo_entrepreneur_present.boolean = True
    photo_entrepreneur_present.short_description = 'Photo (entrepreneur)'

    def photo_enterprise_present(self, obj):
        return bool(getattr(obj, 'photo_enterprise'))
    photo_enterprise_present.boolean = True
    photo_enterprise_present.short_description = 'Photo (enterprise)'


@admin.register(EnterpriseProduct)
class EnterpriseProductAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'enterprise_id',
        'main_product_name',
        'activity_or_product_type',
        'sales_area',
        'avg_monthly_sales',
        'created_at',
    )
    search_fields = ['enterprise_id', 'main_product_name', 'activity_or_product_type']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']


@admin.register(EnterpriseTypeCategory)
class EnterpriseTypeCategoryAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'enterprise_id',
        'form_type',
        'parent_category',
        'sub_category',
        'created_at',
    )
    search_fields = ['enterprise_id', 'parent_category', 'sub_category']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']


@admin.register(NoEnterpriseForm)
class NoEnterpriseFormAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'recorded_benef_id',
        'if_shg_member_inv',
        'is_training_required',
        'future_willing',
        'has_shg_cif',
        'cif_fund_amt',
        'created_at',
    )
    search_fields = ['recorded_benef_id']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']


@admin.register(NoEnterpriseWage)
class NoEnterpriseWageAdmin(admin.ModelAdmin):
    list_display = (
        'TH_urid',
        'enterprise_id',
        'placement_sector',
        'type_of_emp',
        'exp_salary',
        'location_scope',
        'location',
        'created_at',
    )
    search_fields = ['enterprise_id', 'placement_sector', 'location']
    readonly_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']
