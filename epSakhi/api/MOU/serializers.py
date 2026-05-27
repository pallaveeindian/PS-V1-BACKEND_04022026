import re
from datetime import date
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from epSakhi.models import *

# --- REUSABLE VALIDATORS ---

def validate_indian_phone(value):
    """Validates 10-digit Indian phone numbers."""
    if value and not re.match(r'^[6-9]\d{9}$', value):
        raise serializers.ValidationError("Enter a valid 10-digit contact number.")
    return value

def validate_file_size(value):
    """Restricts file uploads to 5MB."""
    limit = 5 * 1024 * 1024  # 5 MB
    if value and value.size > limit:
        raise ValidationError('File size cannot exceed 5 MB.')
    return value

# --- SERIALIZERS ---

class MOUEnterpriseSerializer(serializers.ModelSerializer):
    entrepreneur_contact = serializers.CharField(
        validators=[validate_indian_phone], 
        required=False, 
        allow_blank=True
    )
    entrepeneur_picture = serializers.ImageField(
        validators=[validate_file_size], 
        required=False, 
        allow_null=True
    )

    class Meta:
        model = MOUEnterprise
        fields = '__all__'

    def validate(self, data):
        # Validation: If LokOS SHG code is provided, Name must also be provided (and vice versa)
        shg_code = data.get('lokos_shg_code')
        shg_name = data.get('lokos_shg_name')
        if bool(shg_code) != bool(shg_name):
            raise serializers.ValidationError(
                {"lokos_shg": "Both LokOS SHG Code and Name must be provided together."}
            )

        # Validation: Same rule for CLF
        clf_code = data.get('lokos_clf_code')
        clf_name = data.get('lokos_clf_name')
        if bool(clf_code) != bool(clf_name):
            raise serializers.ValidationError(
                {"lokos_clf": "Both LokOS CLF Code and Name must be provided together."}
            )
            
        return data


class MOUSerializer(serializers.ModelSerializer):
    class Meta:
        model = MOU
        fields = '__all__'

    def validate_mou_date(self, value):
        """MOU date cannot be in the future."""
        if value and value > date.today():
            raise serializers.ValidationError("MOU date cannot be a future date.")
        return value


class MOUDocsSerializer(serializers.ModelSerializer):
    doc_file = serializers.FileField(validators=[validate_file_size], required=False, allow_null=True)

    class Meta:
        model = MOUDocs
        fields = '__all__'

    def validate_doc_file(self, value):
        """Restrict allowed document types."""
        if value:
            valid_extensions = ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx']
            ext = value.name.split('.')[-1].lower()
            if ext not in valid_extensions:
                raise serializers.ValidationError("Unsupported file extension. Upload PDF, JPG, PNG, or DOC.")
        return value


class MOUOrgSerializer(serializers.ModelSerializer):
    org_contact = serializers.CharField(
        validators=[validate_indian_phone], 
        required=False, 
        allow_blank=True
    )

    class Meta:
        model = MOUOrg
        fields = '__all__'


class MOUTradersSerializer(serializers.ModelSerializer):
    trader_contact = serializers.CharField(
        validators=[validate_indian_phone], 
        required=False, 
        allow_blank=True
    )

    class Meta:
        model = MOUTraders
        fields = '__all__'


class MOUProductsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MOUProducts
        fields = '__all__'


class MOUProdCategoriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = MOUProdCategories
        fields = '__all__'

    def validate(self, data):
        # Validation: A child category shouldn't exist without a parent category
        parent = data.get('parent_category')
        child = data.get('child_category')
        
        if child and not parent:
            raise serializers.ValidationError(
                {"parent_category": "A parent category is required if a child category is provided."}
            )
        return data


class MOUSalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = MOUSales
        fields = '__all__'

    def validate(self, data):
        monthly = data.get('est_monthly_sales')
        annual = data.get('est_annual_sales')

        # Prevent negative values
        if monthly is not None and monthly < 0:
            raise serializers.ValidationError({"est_monthly_sales": "Sales cannot be negative."})
        if annual is not None and annual < 0:
            raise serializers.ValidationError({"est_annual_sales": "Sales cannot be negative."})

        # Logic Check: Annual sales should mathematically be at least equal to monthly sales
        if monthly is not None and annual is not None:
            if annual < monthly:
                raise serializers.ValidationError(
                    {"est_annual_sales": "Estimated annual sales cannot be less than monthly sales."}
                )
            
            # Optional strict logic: if annual is wildly off from monthly * 12
            # if annual > (monthly * 12 * Decimal('1.5')):  
            #     raise serializers.ValidationError(...)
                
        return data

# --- List API Serializers (for optimized list views) ---
class MOUEnterpriseListSerializer(serializers.ModelSerializer):

    district_name = serializers.CharField(
        source="district.district_name_en",
        read_only=True
    )

    block_name = serializers.CharField(
        source="block.block_name_en",
        read_only=True
    )

    panchayat_name = serializers.CharField(
        source="panchayat.panchayat_name_en",
        read_only=True
    )

    class Meta:
        model = MOUEnterprise

        fields = [
            "id",

            "district",
            "district_name",

            "block",
            "block_name",

            "panchayat",
            "panchayat_name",

            "lokos_shg_code",
            "lokos_shg_name",

            "lokos_clf_code",
            "lokos_clf_name",

            "enterprise_name",
            "entrepreneur_name",
            "entrepreneur_contact",
            "entrepeneur_picture",
        ]