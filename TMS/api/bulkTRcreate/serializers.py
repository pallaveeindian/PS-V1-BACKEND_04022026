from rest_framework import serializers
from core.models import (
    MasterUser,
    MasterDistrict,
    MasterBlock,
    MasterPanchayat,
    MasterVillage,
)
from TMS.models import (
    TrainingPlan,
    TrainingPartner,
    TrainingTheme,
    MasterTrainer,
    StaffProfile,
    TrainingRequest,
    TRBeneficiary,
    TRTrainer,
    TRStaff,
)


# =====================================================================
# 1. PARTICIPANT INPUT SERIALIZERS (BY TYPE)
# =====================================================================

class OneShotTRBeneficiaryInputSerializer(serializers.Serializer):
    lokos_shg_code = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    lokos_shg_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    lokos_member_code = serializers.CharField(max_length=100, required=True)
    member_name = serializers.CharField(max_length=255, required=True)

    relation = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    relation_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)

    age = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    gender = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    designation = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True, default="")
    pld_status = serializers.CharField(max_length=50, required=False, allow_blank=True, default="NO")

    social_category = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True, default="")
    religion = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True, default="")

    mobile = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True, default="")
    email = serializers.CharField(max_length=254, required=False, allow_blank=True, allow_null=True, default="")
    education = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")

    district = serializers.PrimaryKeyRelatedField(
        queryset=MasterDistrict.objects.all(), required=False, allow_null=True
    )
    block = serializers.PrimaryKeyRelatedField(
        queryset=MasterBlock.objects.all(), required=False, allow_null=True
    )
    panchayat = serializers.PrimaryKeyRelatedField(
        queryset=MasterPanchayat.objects.all(), required=False, allow_null=True
    )
    village = serializers.PrimaryKeyRelatedField(
        queryset=MasterVillage.objects.all(), required=False, allow_null=True
    )

    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")

    def to_internal_value(self, data):
        # Gracefully normalize frontend key variations (e.g., district_id -> district)
        mutable = dict(data) if isinstance(data, dict) else data
        if isinstance(mutable, dict):
            for field in ["district", "block", "panchayat", "village"]:
                if f"{field}_id" in mutable and field not in mutable:
                    mutable[field] = mutable[f"{field}_id"]
                if mutable.get(field) in ["", "-"]:
                    mutable[field] = None

            if not mutable.get("pld_status"):
                mutable["pld_status"] = "NO"
            else:
                raw_pld = str(mutable["pld_status"]).strip().upper()
                mutable["pld_status"] = "YES" if raw_pld in ["TRUE", "1", "YES"] else "NO"

        return super().to_internal_value(mutable)


class OneShotTRTrainerInputSerializer(serializers.Serializer):
    trainer = serializers.PrimaryKeyRelatedField(
        queryset=MasterTrainer.objects.filter(is_active=True), required=True
    )
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True, allow_null=True)
    mobile_no = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    aadhaar_no = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True, default="")

    district = serializers.PrimaryKeyRelatedField(
        queryset=MasterDistrict.objects.all(), required=False, allow_null=True
    )
    block = serializers.PrimaryKeyRelatedField(
        queryset=MasterBlock.objects.all(), required=False, allow_null=True
    )
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")

    def to_internal_value(self, data):
        mutable = dict(data) if isinstance(data, dict) else data
        if isinstance(mutable, dict):
            # Support passing trainer id as `id` or `trainer_id`
            if "trainer" not in mutable:
                mutable["trainer"] = mutable.get("trainer_id") or mutable.get("id")
            if "district" not in mutable and ("empanel_district" in mutable or "district_id" in mutable):
                mutable["district"] = mutable.get("empanel_district") or mutable.get("district_id")
            if "block" not in mutable and ("empanel_block" in mutable or "block_id" in mutable):
                mutable["block"] = mutable.get("empanel_block") or mutable.get("block_id")

            for field in ["district", "block"]:
                if mutable.get(field) in ["", "-"]:
                    mutable[field] = None

        return super().to_internal_value(mutable)


class OneShotTRStaffInputSerializer(serializers.Serializer):
    staff = serializers.PrimaryKeyRelatedField(
        queryset=StaffProfile.objects.filter(is_active=True), required=True
    )
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    designation = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    theme = serializers.PrimaryKeyRelatedField(
        queryset=TrainingTheme.objects.all(), required=False, allow_null=True
    )
    district = serializers.PrimaryKeyRelatedField(
        queryset=MasterDistrict.objects.all(), required=False, allow_null=True
    )
    block = serializers.PrimaryKeyRelatedField(
        queryset=MasterBlock.objects.all(), required=False, allow_null=True
    )
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")

    def to_internal_value(self, data):
        mutable = dict(data) if isinstance(data, dict) else data
        if isinstance(mutable, dict):
            # Support passing staff id as `id` or `staff_id`
            if "staff" not in mutable:
                mutable["staff"] = mutable.get("staff_id") or mutable.get("id")
            if isinstance(mutable.get("theme"), dict):
                mutable["theme"] = mutable["theme"].get("id")
            if isinstance(mutable.get("district"), dict):
                mutable["district"] = mutable["district"].get("district_id") or mutable["district"].get("id")
            if isinstance(mutable.get("block"), dict):
                mutable["block"] = mutable["block"].get("block_id") or mutable["block"].get("id")

            for field in ["theme", "district", "block"]:
                if f"{field}_id" in mutable and field not in mutable:
                    mutable[field] = mutable[f"{field}_id"]
                if mutable.get(field) in ["", "-"]:
                    mutable[field] = None

        return super().to_internal_value(mutable)


# =====================================================================
# 2. SINGLE TRAINING REQUEST + PARTICIPANTS SERIALIZER
# =====================================================================

class SingleTrainingRequestOneShotSerializer(serializers.Serializer):
    financial_year = serializers.CharField(max_length=9, required=True)
    training_plan = serializers.PrimaryKeyRelatedField(
        queryset=TrainingPlan.objects.filter(is_active=True), required=True
    )
    partner = serializers.PrimaryKeyRelatedField(
        queryset=TrainingPartner.objects.filter(is_active=True), required=True
    )
    training_type = serializers.ChoiceField(
        choices=TrainingRequest.TRAINING_TYPE_CHOICES, required=True
    )
    level = serializers.ChoiceField(
        choices=TrainingRequest.LEVEL_CHOICES, default="BLOCK", required=False
    )
    status = serializers.ChoiceField(
        choices=TrainingRequest.STATUS_CHOICES, default="BATCHING", required=False
    )
    district = serializers.PrimaryKeyRelatedField(
        queryset=MasterDistrict.objects.all(), required=True
    )
    block = serializers.PrimaryKeyRelatedField(
        queryset=MasterBlock.objects.all(), required=False, allow_null=True
    )
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    is_old = serializers.BooleanField(default=False, required=False)
    created_by = serializers.PrimaryKeyRelatedField(
        queryset=MasterUser.objects.all(), required=False, allow_null=True
    )

    # Flexible participant lists: caller can pass `participants` OR type-specific keys
    participants = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )
    beneficiaries = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )
    trainers = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )
    staff = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )

    def to_internal_value(self, data):
        mutable = dict(data) if isinstance(data, dict) else data
        if isinstance(mutable, dict):
            if "Block" in mutable or "block" in mutable:
                if mutable.get("block") in ["", "-"]:
                    mutable["block"] = None
            if "district_id" in mutable and "district" not in mutable:
                mutable["district"] = mutable["district_id"]
            if "block_id" in mutable and "block" not in mutable:
                mutable["block"] = mutable["block_id"]
            if "training_plan_id" in mutable and "training_plan" not in mutable:
                mutable["training_plan"] = mutable["training_plan_id"]
            if "partner_id" in mutable and "partner" not in mutable:
                mutable["partner"] = mutable["partner_id"]
        return super().to_internal_value(mutable)

    def validate_financial_year(self, value):
        val = (value or "").strip()
        if len(val) < 5 or "-" not in val:
            raise serializers.ValidationError("Invalid financial_year format (expected e.g. '2026-27').")
        return val

    def validate(self, attrs):
        t_type = attrs.get("training_type")

        # 1. Enforce STATE level for STAFF training requests
        if t_type == "STAFF":
            attrs["level"] = "STATE"

        # 2. Consolidate notes -> remarks
        if not attrs.get("remarks") and attrs.get("notes"):
            attrs["remarks"] = attrs.get("notes")

        # 3. Extract raw participant list based on training_type or generic `participants` key
        raw_participants = attrs.get("participants")
        if raw_participants is None:
            if t_type == "BENEFICIARY":
                raw_participants = attrs.get("beneficiaries")
            elif t_type == "TRAINER":
                raw_participants = attrs.get("trainers")
            elif t_type == "STAFF":
                raw_participants = attrs.get("staff")

        if not raw_participants or not isinstance(raw_participants, list) or len(raw_participants) == 0:
            raise serializers.ValidationError({
                "participants": f"At least 1 participant is required for a {t_type} Training Request."
            })

        # 4. Validate each participant using the appropriate sub-serializer & deduplicate
        validated_participants = []
        seen_keys = set()

        if t_type == "BENEFICIARY":
            sub_serializer = OneShotTRBeneficiaryInputSerializer(data=raw_participants, many=True)
            sub_serializer.is_valid(raise_exception=True)

            for item in sub_serializer.validated_data:
                m_code = str(item["lokos_member_code"]).strip()
                if m_code in seen_keys:
                    raise serializers.ValidationError({
                        "participants": f"Duplicate beneficiary lokos_member_code '{m_code}' in the same request."
                    })
                seen_keys.add(m_code)
                validated_participants.append(item)

        elif t_type == "TRAINER":
            sub_serializer = OneShotTRTrainerInputSerializer(data=raw_participants, many=True)
            sub_serializer.is_valid(raise_exception=True)

            for item in sub_serializer.validated_data:
                trainer_obj = item["trainer"]
                if trainer_obj.id in seen_keys:
                    raise serializers.ValidationError({
                        "participants": f"Duplicate MasterTrainer ID '{trainer_obj.id}' in the same request."
                    })
                seen_keys.add(trainer_obj.id)
                validated_participants.append(item)

        elif t_type == "STAFF":
            sub_serializer = OneShotTRStaffInputSerializer(data=raw_participants, many=True)
            sub_serializer.is_valid(raise_exception=True)

            for item in sub_serializer.validated_data:
                staff_obj = item["staff"]
                if staff_obj.id in seen_keys:
                    raise serializers.ValidationError({
                        "participants": f"Duplicate StaffProfile ID '{staff_obj.id}' in the same request."
                    })
                seen_keys.add(staff_obj.id)
                validated_participants.append(item)

        attrs["validated_participants"] = validated_participants
        return attrs


# =====================================================================
# 3. MASTER BULK WRAPPER SERIALIZER (SUPPORTS 1 OR MANY TRs)
# =====================================================================

class BulkTrainingRequestOneShotSerializer(serializers.Serializer):
    training_requests = SingleTrainingRequestOneShotSerializer(many=True)

    def to_internal_value(self, data):
        """
        Allows the frontend to send:
        1. { "training_requests": [ { ... }, { ... } ] }
        2. [ { ... }, { ... } ]  (Direct array of TRs)
        3. { "financial_year": "...", "training_plan": 1, "participants": [...] } (Single TR object)
        """
        if isinstance(data, list):
            normalized = {"training_requests": data}
        elif isinstance(data, dict) and "training_requests" not in data:
            normalized = {"training_requests": [data]}
        else:
            normalized = data

        return super().to_internal_value(normalized)

    def validate_training_requests(self, value):
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one Training Request must be provided.")
        return value