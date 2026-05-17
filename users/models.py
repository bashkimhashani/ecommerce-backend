from pathlib import Path
from uuid import uuid4

from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin
)
from tenants.models import Tenant


def user_avatar_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower() or '.jpg'
    return f'users/{instance.pk}/avatars/{uuid4().hex}{suffix}'


def user_avatar_thumbnail_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower() or '.jpg'
    return f'users/{instance.pk}/avatars/thumbnails/{uuid4().hex}{suffix}'


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'superadmin')
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):

    ROLE_CHOICES = [
        ('superadmin', 'Super Admin'),
        ('vendor_admin', 'Vendor Admin'),
        ('store_staff', 'Store Staff'),
        ('customer', 'Customer'),
    ]

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='customer'
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users'
    )
    phone = models.CharField(max_length=20, null=True, blank=True)
    avatar = models.ImageField(
        upload_to=user_avatar_upload_path,
        null=True,
        blank=True,
    )
    avatar_thumbnail = models.ImageField(
        upload_to=user_avatar_thumbnail_upload_path,
        null=True,
        blank=True,
        editable=False,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'
