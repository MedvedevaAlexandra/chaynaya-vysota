import re

from rest_framework import serializers

PHONE_REGEX = re.compile(r"^\+[1-9]\d{6,14}$")


def validate_phone(value: str) -> str:
    if not PHONE_REGEX.match(value):
        raise serializers.ValidationError(
            "Phone must be in E.164 format: '+' followed by country code and number (7-15 digits total)."
        )
    return value


class PhoneSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, validators=[validate_phone])


class GuestRegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, validators=[validate_phone], required=False)
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    tg = serializers.CharField(max_length=64, required=False, allow_blank=True)


class GuestAuthSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, validators=[validate_phone])
    name = serializers.CharField(max_length=150)


class GuestAuthResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    created = serializers.BooleanField()


class GuestProfileUpdateSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, validators=[validate_phone], required=False)
    name = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    tg = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one of 'phone', 'name', 'email' or 'tg' must be provided.")
        return attrs


class GuestProfileSerializer(serializers.Serializer):
    phone = serializers.CharField(allow_null=True)
    name = serializers.CharField(source="first_name", allow_blank=True)
    email = serializers.CharField(allow_blank=True)
    tg = serializers.CharField(allow_null=True, allow_blank=True)


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
