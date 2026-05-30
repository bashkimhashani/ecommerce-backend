import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from vendor.models import VendorProfile

from .models import Tenant

User = get_user_model()

DOMAIN_PATTERN = (
    r"^(?=.{1,255}$)(?!-)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}$"
)


def validate_unique_tenant_field(field_name, value, instance=None):
    queryset = Tenant.objects.filter(**{field_name: value})
    if instance and instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    if queryset.exists():
        raise serializers.ValidationError(
            f"A tenant with this {field_name} already exists."
        )
    return value


def validate_tenant_domain(value, instance=None):
    domain = value.lower().strip()
    if not re.fullmatch(DOMAIN_PATTERN, domain):
        raise serializers.ValidationError("Enter a valid domain name.")
    return validate_unique_tenant_field("domain", domain, instance)


class TenantSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    slug = serializers.SlugField(max_length=50)
    domain = serializers.CharField(max_length=255)

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "slug",
            "domain",
            "owner",
            "plan",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def validate_slug(self, value):
        return validate_unique_tenant_field("slug", value, self.instance)

    def validate_domain(self, value):
        return validate_tenant_domain(value, self.instance)


class TenantRegistrationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=50)
    domain = serializers.CharField(max_length=255)
    plan = serializers.ChoiceField(
        choices=Tenant.PLAN_CHOICES,
        default="free",
        required=False,
    )
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    password = serializers.CharField(write_only=True, min_length=8)
    phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user and user.is_authenticated:
            for field_name in ["email", "first_name", "last_name", "password"]:
                self.fields[field_name].required = False

    def validate_slug(self, value):
        return validate_unique_tenant_field("slug", value)

    def validate_domain(self, value):
        return validate_tenant_domain(value)

    def validate_email(self, value):
        email = User.objects.normalize_email(value)
        request = self.context.get("request")
        current_user = getattr(request, "user", None)
        users = User.objects.filter(email=email)
        if current_user and current_user.is_authenticated:
            users = users.exclude(pk=current_user.pk)
        if users.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user and user.is_authenticated:
            if user.tenant_id:
                raise serializers.ValidationError(
                    "This account is already connected to a vendor tenant."
                )
            return attrs

        required_fields = ["email", "first_name", "last_name", "password"]
        missing_fields = [field for field in required_fields if not attrs.get(field)]
        if missing_fields:
            raise serializers.ValidationError(
                {field: "This field is required." for field in missing_fields}
            )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        existing_user = getattr(request, "user", None)
        use_existing_user = bool(existing_user and existing_user.is_authenticated)

        if use_existing_user:
            user_data = {}
            validated_data.pop("email", None)
            validated_data.pop("first_name", None)
            validated_data.pop("last_name", None)
            validated_data.pop("password", None)
            phone = validated_data.pop("phone", "")
        else:
            user_data = {
                "email": validated_data.pop("email"),
                "password": validated_data.pop("password"),
                "first_name": validated_data.pop("first_name"),
                "last_name": validated_data.pop("last_name"),
                "phone": validated_data.pop("phone", ""),
            }
            phone = user_data.get("phone", "")

        with transaction.atomic():
            tenant = Tenant.objects.create(**validated_data)
            if use_existing_user:
                user = existing_user
                user.role = "vendor_admin"
                user.tenant = tenant
                if phone and not user.phone:
                    user.phone = phone
                user.save(update_fields=["role", "tenant", "phone"])
            else:
                user = User.objects.create_user(
                    **user_data,
                    role="vendor_admin",
                    tenant=tenant,
                )
            tenant.owner = user
            tenant.save(update_fields=["owner"])
            VendorProfile.objects.create(
                user=user,
                tenant=tenant,
                store_name=tenant.name,
                contact_email=user.email,
                contact_phone=user.phone,
                is_active=True,
            )
            self.create_default_catalog(tenant)

        return {
            "tenant": tenant,
            "user": user,
        }

    def create_default_catalog(self, tenant):
        from catalog.models import Brand, Category

        default_brand_name = tenant.name
        Brand.objects.create(
            tenant=tenant,
            name=default_brand_name,
            slug=slugify(default_brand_name)[:255] or f"brand-{tenant.id}",
        )
        Category.objects.create(
            tenant=tenant,
            name="General",
            slug="general",
            is_active=True,
        )
