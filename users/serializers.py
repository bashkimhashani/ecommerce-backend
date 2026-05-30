from io import BytesIO
from pathlib import Path

from rest_framework import serializers
from django.contrib.auth import password_validation
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.files.base import ContentFile
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from PIL import Image
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .tokens import email_verification_token_generator

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["tenant_id"] = user.tenant_id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user, context=self.context).data
        data["role"] = self.user.role
        data["tenant_id"] = self.user.tenant_id
        return data


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "password", "role"]

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            role=validated_data.get("role", "customer"),
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "tenant",
            "phone",
            "is_email_verified",
            "avatar",
            "avatar_thumbnail",
            "date_joined",
        ]
        read_only_fields = ["avatar_thumbnail"]


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "tenant",
            "phone",
            "is_email_verified",
            "avatar",
            "avatar_thumbnail",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "email",
            "role",
            "tenant",
            "is_email_verified",
            "avatar_thumbnail",
            "date_joined",
        ]

    def update(self, instance, validated_data):
        avatar_was_provided = "avatar" in validated_data
        old_avatar_name = instance.avatar.name if instance.avatar else None
        old_thumbnail_name = (
            instance.avatar_thumbnail.name if instance.avatar_thumbnail else None
        )

        instance = super().update(instance, validated_data)

        if avatar_was_provided:
            if instance.avatar:
                self.generate_avatar_thumbnail(instance)
            else:
                instance.avatar_thumbnail.delete(save=False)
                instance.avatar_thumbnail = None
                instance.save(update_fields=["avatar_thumbnail"])

            self.delete_replaced_file(instance.avatar, old_avatar_name)
            self.delete_replaced_file(
                instance.avatar_thumbnail,
                old_thumbnail_name,
            )

        return instance

    def generate_avatar_thumbnail(self, instance):
        instance.avatar.open("rb")
        image = Image.open(instance.avatar)
        image.load()
        instance.avatar.close()

        image.thumbnail((256, 256), Image.Resampling.LANCZOS)
        if image.mode in ("RGBA", "LA"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        output = BytesIO()
        image.save(output, format="JPEG", quality=85, optimize=True)
        output.seek(0)

        thumbnail_name = self.get_thumbnail_name(instance, instance.avatar.name)
        instance.avatar_thumbnail.save(
            thumbnail_name,
            ContentFile(output.read()),
            save=False,
        )
        instance.save(update_fields=["avatar_thumbnail"])

    def get_thumbnail_name(self, instance, avatar_name):
        return (
            f"users/{instance.pk}/avatars/thumbnails/"
            f"{Path(avatar_name).stem}_thumbnail.jpg"
        )

    def delete_replaced_file(self, current_file, old_name):
        if not old_name:
            return
        if current_file and current_file.name == old_name:
            return
        current_file.storage.delete(old_name)


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailVerificationSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError(
                {"token": "Invalid email verification token."}
            )

        if not email_verification_token_generator.check_token(
            user,
            attrs["token"],
        ):
            raise serializers.ValidationError(
                {"token": "Invalid or expired email verification token."}
            )

        attrs["user"] = user
        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError(
                {"token": "Invalid password reset token."}
            )

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                {"token": "Invalid or expired password reset token."}
            )

        password_validation.validate_password(
            attrs["new_password"],
            user,
        )
        attrs["user"] = user
        return attrs
