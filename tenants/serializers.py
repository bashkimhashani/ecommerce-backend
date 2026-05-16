import re

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import Tenant


User = get_user_model()


class TenantSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

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
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError(
                'A tenant with this slug already exists.'
            )
        return value

    def validate_domain(self, value):
        domain = value.lower().strip()
        domain_pattern = (
            r'^(?=.{1,255}$)(?!-)'
            r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+'
            r'[a-z]{2,63}$'
        )
        if not re.fullmatch(domain_pattern, domain):
            raise serializers.ValidationError('Enter a valid domain name.')
        if Tenant.objects.filter(domain=domain).exists():
            raise serializers.ValidationError(
                'A tenant with this domain already exists.'
            )
        return domain

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
