from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from catalog.models import ProductReview, ProductTastingUserMark, TastingParticipation

from .models import User


class UserTastingParticipationInline(admin.TabularInline):
    model = TastingParticipation
    fk_name = "user"
    extra = 0
    can_delete = False
    fields = ("tasting", "joined_at")
    readonly_fields = ("tasting", "joined_at")
    ordering = ("-joined_at",)
    verbose_name = "Участие в дегустации"
    verbose_name_plural = "Участия в дегустациях (read-only)"

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("tasting")


class UserProductReviewInline(admin.TabularInline):
    model = ProductReview
    fk_name = "user"
    extra = 0
    can_delete = False
    fields = ("product", "tasted", "is_bookmarked", "global_comment", "updated_at")
    readonly_fields = ("product", "tasted", "is_bookmarked", "global_comment", "updated_at")
    ordering = ("-updated_at",)
    verbose_name = "Отзыв"
    verbose_name_plural = "Отзывы (read-only)"

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product")


class UserProductTastingMarkInline(admin.TabularInline):
    model = ProductTastingUserMark
    fk_name = "user"
    extra = 0
    can_delete = False
    fields = ("tasting", "product_tasting", "is_nominated", "podium_place", "updated_at")
    readonly_fields = ("tasting", "product_tasting", "is_nominated", "podium_place", "updated_at")
    ordering = ("tasting", "podium_place", "-updated_at")
    verbose_name = "Метка в дегустации"
    verbose_name_plural = "Номинации и подиумы (read-only)"

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("tasting", "product_tasting__product")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("Loyalty", {"fields": ("phone", "tg", "has_loyalty")}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("Loyalty", {"fields": ("phone", "tg", "has_loyalty")}),)
    list_display = BaseUserAdmin.list_display + ("phone", "tg", "has_loyalty")
    list_filter = BaseUserAdmin.list_filter + ("has_loyalty",)
    search_fields = BaseUserAdmin.search_fields + ("phone", "tg", "id")
    inlines = [
        UserTastingParticipationInline,
        UserProductReviewInline,
        UserProductTastingMarkInline,
    ]
