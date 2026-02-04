# epSakhi/api/serializers.py

from django.db import transaction
from rest_framework import serializers

from epSakhi.models import (
    CRPEP,
    BeneficiaryRecorded,
    ExistingEnterprise,
    NewEnterprise,
    EnterpriseLoanDetail,
    EnterpriseSubsidyDetail,   # NEW model name (replaces EnterpriseSupportDetail)
    EnterpriseTrainingReq,
    EnterpriseMedia,
    EnterpriseProduct,         # NEW
    EnterpriseTypeCategory,    # NEW
    NoEnterpriseForm,          # NEW
    NoEnterpriseWage,          # NEW
)

from core.api.serializers import (
    MasterPanchayatListSerializer,
    MasterBlockListSerializer,
    MasterDistrictListSerializer,
)


class CRPEPSerializer(serializers.ModelSerializer):
    # Nested, read-only related objects (FKs on CRPEP)
    district = MasterDistrictListSerializer(read_only=True)
    block = MasterBlockListSerializer(read_only=True)
    panchayat = MasterPanchayatListSerializer(read_only=True)

    class Meta:
        model = CRPEP
        fields = [
            'id',
            'name',
            'mobile_number',
            'category',
            'subcategory',
            'marks_obtained',
            'TH_urid',
            'district_id',
            'block_id',
            'panchayat_id',
            'lokos_shg_code',
            'lokos_member_code',
            'nodal_clf',
            # nested read-only relations
            'district',
            'block',
            'panchayat',
            'created_at',
            'updated_at',
            'deleted_at',
        ]
        read_only_fields = [
            'created_at',
            'updated_at',
            'deleted_at',
            'TH_urid',
            'district',
            'block',
            'panchayat',
        ]


class BeneficiaryRecordedSerializer(serializers.ModelSerializer):
    class Meta:
        model = BeneficiaryRecorded
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'deleted_at', 'TH_urid']


# ============= DETAIL SERIALIZERS =============

class EnterpriseLoanDetailSerializer(serializers.ModelSerializer):
    """
    Used by:
      - /enterprise-loan-details/
      - (Optionally) nested in ExistingEnterpriseSerializer for read operations.
    """
    class Meta:
        model = EnterpriseLoanDetail
        fields = '__all__'


class EnterpriseSupportDetailSerializer(serializers.ModelSerializer):
    """
    NOTE:
    - Class name kept for backward compatibility.
    - Underlying model is now EnterpriseSubsidyDetail (epSakhi_exEpSubsidy).
    - Used by:
        * /enterprise-support-details/
    """
    class Meta:
        model = EnterpriseSubsidyDetail
        fields = '__all__'


class EnterpriseTrainingReqSerializer(serializers.ModelSerializer):
    """
    Used by:
      - /enterprise-training-reqs/
    """
    class Meta:
        model = EnterpriseTrainingReq
        fields = '__all__'


class EnterpriseMediaSerializer(serializers.ModelSerializer):
    """
    Used by:
      - /enterprise-media/
    """
    class Meta:
        model = EnterpriseMedia
        fields = '__all__'


# ============= EXISTING / NEW ENTERPRISE =============

class ExistingEnterpriseSerializer(serializers.ModelSerializer):
    """
    ExistingEnterprise main form.

    Nested write-only fields (OPTIONAL, kept for backward compatibility):
      - loan_details: [ {...}, ... ]
      - support_detail: { ... }
      - training_reqs: [ {...}, ... ]
      - media: { ... }

    If these keys are omitted in payload, child tables are untouched.
    """

    loan_details = EnterpriseLoanDetailSerializer(
        many=True, write_only=True, required=False
    )
    support_detail = EnterpriseSupportDetailSerializer(
        write_only=True, required=False
    )
    training_reqs = EnterpriseTrainingReqSerializer(
        many=True, write_only=True, required=False
    )
    media = EnterpriseMediaSerializer(
        write_only=True, required=False
    )

    class Meta:
        model = ExistingEnterprise
        fields = '__all__'
        read_only_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']

    @transaction.atomic
    def create(self, validated_data):
        loan_data = validated_data.pop('loan_details', None)
        support_data = validated_data.pop('support_detail', None)
        training_data = validated_data.pop('training_reqs', None)
        media_data = validated_data.pop('media', None)

        enterprise = super().create(validated_data)
        enterprise_id = enterprise.TH_urid

        # ----- Loan details -----
        if loan_data:
            for ld in loan_data:
                EnterpriseLoanDetail.objects.create(
                    enterprise_id=enterprise_id,
                    **ld
                )

        # ----- Subsidy (support) detail -----
        if support_data:
            EnterpriseSubsidyDetail.objects.create(
                enterprise_id=enterprise_id,
                **support_data
            )

        # ----- Training requirements -----
        if training_data:
            for tr in training_data:
                EnterpriseTrainingReq.objects.create(
                    enterprise_id=enterprise_id,
                    **tr
                )

        # ----- Media -----
        if media_data:
            EnterpriseMedia.objects.create(
                enterprise_id=enterprise_id,
                **media_data
            )

        return enterprise

    @transaction.atomic
    def update(self, instance, validated_data):
        loan_data = validated_data.pop('loan_details', None)
        support_data = validated_data.pop('support_detail', None)
        training_data = validated_data.pop('training_reqs', None)
        media_data = validated_data.pop('media', None)

        enterprise = super().update(instance, validated_data)
        enterprise_id = enterprise.TH_urid

        # ----- Loan details -----
        if loan_data is not None:
            EnterpriseLoanDetail.objects.filter(enterprise_id=enterprise_id).delete()
            for ld in loan_data:
                EnterpriseLoanDetail.objects.create(
                    enterprise_id=enterprise_id,
                    **ld
                )

        # ----- Subsidy (support) detail -----
        if support_data is not None:
            EnterpriseSubsidyDetail.objects.filter(enterprise_id=enterprise_id).delete()
            if support_data:
                EnterpriseSubsidyDetail.objects.create(
                    enterprise_id=enterprise_id,
                    **support_data
                )

        # ----- Training requirements -----
        if training_data is not None:
            EnterpriseTrainingReq.objects.filter(enterprise_id=enterprise_id).delete()
            for tr in training_data:
                EnterpriseTrainingReq.objects.create(
                    enterprise_id=enterprise_id,
                    **tr
                )

        # ----- Media -----
        if media_data is not None:
            EnterpriseMedia.objects.filter(enterprise_id=enterprise_id).delete()
            if media_data:
                EnterpriseMedia.objects.create(
                    enterprise_id=enterprise_id,
                    **media_data
                )

        return enterprise


class NewEnterpriseSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewEnterprise
        fields = '__all__'
        read_only_fields = ['TH_urid', 'created_at', 'updated_at', 'deleted_at']


# ============= NEW DETAIL MODELS =============

class EnterpriseProductSerializer(serializers.ModelSerializer):
    """
    CRUD for epSakhi_exEpProduct
    """
    class Meta:
        model = EnterpriseProduct
        fields = '__all__'


class EnterpriseTypeCategorySerializer(serializers.ModelSerializer):
    """
    CRUD for epSakhi_epType
    """
    class Meta:
        model = EnterpriseTypeCategory
        fields = '__all__'


class NoEnterpriseFormSerializer(serializers.ModelSerializer):
    """
    CRUD for epSakhi_noEpForm
    """
    class Meta:
        model = NoEnterpriseForm
        fields = '__all__'


class NoEnterpriseWageSerializer(serializers.ModelSerializer):
    """
    CRUD for epSakhi_noEpWage
    """
    class Meta:
        model = NoEnterpriseWage
        fields = '__all__'
