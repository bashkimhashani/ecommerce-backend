import re

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import Tenant


User = get_user_model()

DOMAIN_PATTERN = (
    r'^(?=.{1,255}$)(?!-)'
    r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+'
    r'[a-z]{2,63}$'
)


def validate_unique_tenant_field(field_name, value, instance=None):
    queryset = Tenant.objects.filter(**{field_name: value})
    if instance and instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    if queryset.exists():
        raise serializers.ValidationError(
            f'A tenant with this {field_name} already exists.'
        )
    return value


def validate_tenant_domain(value, instance=None):
    domain = value.lower().strip()
    if not re.fullmatch(DOMAIN_PATTERN, domain):
        raise serializers.ValidationError('Enter a valid domain name.')
    return validate_unique_tenant_field('domain', domain, instance)


class TenantSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    slug = serializers.SlugField(max_length=50)
    domain = serializers.CharField(max_length=255)

    class Meta:
        model = Tenant
        fields = [
            'id',
            'name',
            'slug',
            'domain',
            'owner',
            'plan',
            'is_active',
            'created_at',
            'updated_at',
        ]

    def validate_slug(self, value):
        return validate_unique_tenant_field('slug', value, self.instance)

    def validate_domain(self, value):
        return validate_tenant_domain(value, self.instance)


class TenantRegistrationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=50)
    domain = serializers.CharField(max_length=255)
    plan = serializers.ChoiceField(
        choices=Tenant.PLAN_CHOICES,
        default='free',
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

    def validate_slug(self, value):
        return validate_unique_tenant_field('slug', value)

    def validate_domain(self, value):
        return validate_tenant_domain(value)

    def validate_email(self, value):
        email = User.objects.normalize_email(value)
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                'A user with this email already exists.'
            )
        return email

    def create(self, validated_data):
        user_data = {
            'email': validated_data.pop('email'),
            'password': validated_data.pop('password'),
            'first_name': validated_data.pop('first_name'),
            'last_name': validated_data.pop('last_name'),
            'phone': validated_data.pop('phone', ''),
        }

        with transaction.atomic():
            tenant = Tenant.objects.create(**validated_data)
            user = User.objects.create_user(
                **user_data,
                role='vendor_admin',
                tenant=tenant,
            )
            tenant.owner = user
            tenant.save(update_fields=['owner'])

        return {
            'tenant': tenant,
            'user': user,
        }
