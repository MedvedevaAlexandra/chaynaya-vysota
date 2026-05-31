import uuid

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    GuestAuthResponseSerializer,
    GuestAuthSerializer,
    GuestProfileSerializer,
    GuestProfileUpdateSerializer,
    GuestRegisterSerializer,
    PhoneSerializer,
    TokenPairSerializer,
)

User = get_user_model()


def _issue_tokens(user) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _generate_username() -> str:
    return f"guest_{uuid.uuid4().hex[:12]}"


class GuestRegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=GuestRegisterSerializer, responses={201: TokenPairSerializer})
    def post(self, request):
        serializer = GuestRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data.get("phone")
        name = serializer.validated_data["name"]

        if phone and User.objects.filter(phone=phone).exists():
            return Response(
                {"detail": "Guest with this phone already exists."},
                status=status.HTTP_409_CONFLICT,
            )

        user = User.objects.create_user(
            username=_generate_username(),
            phone=phone,
            first_name=name,
            email=serializer.validated_data.get("email", ""),
            tg=serializer.validated_data.get("tg", ""),
        )
        return Response(_issue_tokens(user), status=status.HTTP_201_CREATED)


class GuestAuthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=GuestAuthSerializer, responses={200: GuestAuthResponseSerializer, 201: GuestAuthResponseSerializer})
    def post(self, request):
        serializer = GuestAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        name = serializer.validated_data["name"]

        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={"username": _generate_username(), "first_name": name},
        )

        tokens = _issue_tokens(user)
        return Response(
            {**tokens, "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class GuestLoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=PhoneSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = PhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response(
                {"detail": "Guest with this phone not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(_issue_tokens(user), status=status.HTTP_200_OK)


class GuestMeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: GuestProfileSerializer})
    def get(self, request):
        return Response(GuestProfileSerializer(request.user).data, status=status.HTTP_200_OK)

    @extend_schema(request=GuestProfileUpdateSerializer, responses={200: GuestProfileSerializer})
    def put(self, request):
        serializer = GuestProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        update_fields: list[str] = []

        if "phone" in data:
            phone = data["phone"]
            if User.objects.exclude(pk=user.pk).filter(phone=phone).exists():
                return Response(
                    {"detail": "This phone is already used by another guest."},
                    status=status.HTTP_409_CONFLICT,
                )
            user.phone = phone
            update_fields.append("phone")

        if "name" in data:
            user.first_name = data["name"]
            update_fields.append("first_name")

        if "email" in data:
            user.email = data["email"]
            update_fields.append("email")

        if "tg" in data:
            user.tg = data["tg"]
            update_fields.append("tg")

        user.save(update_fields=update_fields)
        return Response(GuestProfileSerializer(user).data, status=status.HTTP_200_OK)
