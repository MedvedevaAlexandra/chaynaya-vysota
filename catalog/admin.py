from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.html import format_html

from .models import (
    Chart,
    Config,
    IceCreamLogo,
    TasteTags,
    Line,
    FreeTextPrompt,
    FreeTextPromptReview,
    PhraseTemplate,
    PhraseTemplateReview,
    Product,
    ProductCriteriaReview,
    ProductIceCreamLogo,
    ProductPhoto,
    ProductReview,
    ProductTasting,
    ProductTastingChart,
    ProductTastingFreeTextPrompt,
    ProductTastingPhraseTemplate,
    ProductTastingTasteBlock,
    ProductTastingTasteCriteria,
    ProductTastingUserMark,
    TasteBlock,
    TasteCriteria,
    Tasting,
    TastingParticipation,
)


@admin.register(Line)
class LineAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name", "id")
    ordering = ("name",)


@admin.register(TasteTags)
class IceCreamTasteTagsAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "weight")
    list_editable = ("weight",)
    search_fields = ("name", "id")
    ordering = ("name",)


@admin.register(IceCreamLogo)
class IceCreamLogoAdmin(admin.ModelAdmin):
    list_display = ("id", "text", "thumb")
    search_fields = ("text", "id")
    readonly_fields = ("thumb",)

    @admin.display(description="Превью")
    def thumb(self, obj: IceCreamLogo):
        if not obj.image:
            return "—"
        return format_html('<img src="{}" style="height:40px;border-radius:4px"/>', obj.image.url)


@admin.register(TasteBlock)
class TasteBlockAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name", "id")
    ordering = ("name",)


@admin.register(PhraseTemplate)
class PhraseTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "name", "blanks_count", "show_toggle_list", "taste_block")
    list_editable = ("order", "show_toggle_list", "taste_block")
    list_filter = ("taste_block",)
    search_fields = ("name", "template", "id")
    autocomplete_fields = ("taste_block",)
    ordering = ("order", "id")

    @admin.display(description="Пропусков")
    def blanks_count(self, obj: PhraseTemplate) -> int:
        return obj.blanks_count


@admin.register(FreeTextPrompt)
class FreeTextPromptAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "name", "taste_block")
    list_editable = ("order", "taste_block")
    list_filter = ("taste_block",)
    search_fields = ("name", "description", "id")
    autocomplete_fields = ("taste_block",)
    ordering = ("order", "id")


@admin.register(Chart)
class ChartAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "name", "chart_type", "taste_block", "label_placement", "color")
    list_editable = ("order", "chart_type", "taste_block", "label_placement", "color")
    list_filter = ("chart_type", "label_placement", "taste_block")
    search_fields = ("name", "id")
    autocomplete_fields = ("taste_block",)
    ordering = ("order", "id")
    save_on_top = True
    save_as = True  # «Сохранить как новый» — удобно клонировать конфиг чарта
    fieldsets = (
        (None, {"fields": ("name", "description", "order", "color", "chart_type", "taste_block")}),
        ("Круговой чарт", {"fields": ("label_placement",)}),
        (
            "График (Plot)",
            {
                "classes": ("collapse",),
                "description": "Заполняется только при chart_type=График. "
                'x_axis/y_axis — списки делений [{"value": int, "label": str}, ...].',
                "fields": ("x_axis", "x_axis_name", "y_axis", "y_axis_name"),
            },
        ),
    )


@admin.register(TasteCriteria)
class TasteCriteriaAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "name", "orientation", "chart", "taste_block", "grade")
    list_editable = ("order", "orientation", "chart", "taste_block")
    list_filter = ("orientation", "chart", "taste_block")
    search_fields = ("name", "id")
    autocomplete_fields = ("chart", "taste_block")
    ordering = ("order", "id")


class ProductIceCreamLogoInline(admin.TabularInline):
    model = ProductIceCreamLogo
    extra = 0
    autocomplete_fields = ("logo",)


class ProductPhotoInline(admin.TabularInline):
    model = ProductPhoto
    extra = 0
    fields = ("image", "name", "order", "thumb")
    readonly_fields = ("thumb",)
    ordering = ("order", "id")
    verbose_name = "Фото"
    verbose_name_plural = "Фото (загрузить; выбираются в дегустациях)"

    @admin.display(description="Превью")
    def thumb(self, obj: ProductPhoto):
        if not obj.image:
            return "—"
        return format_html('<img src="{}" style="height:40px;border-radius:4px"/>', obj.image.url)


@admin.register(ProductPhoto)
class ProductPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "name", "order", "thumb")
    list_editable = ("name", "order")
    list_filter = ("product__type",)
    search_fields = ("name", "id", "product__name", "product__id")
    autocomplete_fields = ("product",)
    list_select_related = ("product",)
    ordering = ("product", "order", "id")

    @admin.display(description="Превью")
    def thumb(self, obj: ProductPhoto):
        if not obj.image:
            return "—"
        return format_html('<img src="{}" style="height:40px;border-radius:4px"/>', obj.image.url)


class ProductInTastingsInline(admin.TabularInline):
    model = ProductTasting
    extra = 0
    fk_name = "product"
    show_change_link = True  # провалиться в конкретный ProductTasting (там конфиг оценки)
    autocomplete_fields = ("tasting",)
    fields = ("tasting", "category", "order", "tea_flavor_combination")
    ordering = ("tasting__date",)
    verbose_name = "Дегустация"
    verbose_name_plural = "В каких дегустациях"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "type", "line", "thumb")
    list_display_links = ("number", "name")
    list_filter = ("type", "line", "taste_tags")
    search_fields = ("name", "number", "id")
    autocomplete_fields = ("line",)
    filter_horizontal = ("taste_tags",)
    readonly_fields = ("thumb",)
    save_on_top = True
    ordering = ("type", "number", "name")
    fieldsets = (
        (None, {"fields": ("type", "number", "name", "line")}),
        ("Контент", {"fields": ("description", "interesting_fact", "composition", "image", "thumb", "color")}),
        (
            "Чай",
            {
                "classes": ("collapse",),
                "fields": (
                    "tea_nickname",
                    "tea_sort",
                    "tea_index",
                    "tea_price",
                    "tea_measure_unit",
                    "tea_geography",
                    "tea_plucking_season",
                    "tea_rubrucator",
                    "tea_cultivar",
                    "tea_altitude",
                    "tea_color_type_name",
                ),
            },
        ),
        ("Результат", {"fields": ("result_phrase",)}),
        ("Теги", {"fields": ("taste_tags",)}),
    )
    inlines = [ProductPhotoInline, ProductIceCreamLogoInline, ProductInTastingsInline]

    @admin.display(description="Превью")
    def thumb(self, obj: Product):
        if not obj.image:
            return "—"
        return format_html('<img src="{}" style="height:48px;border-radius:4px"/>', obj.image.url)


class TastingParticipationInline(admin.TabularInline):
    model = TastingParticipation
    extra = 0
    readonly_fields = ("joined_at",)
    autocomplete_fields = ("user",)


class ProductTastingInline(admin.TabularInline):
    model = ProductTasting
    extra = 0
    show_change_link = True  # из Tasting → конкретный ProductTasting (критерии/блоки/фразы)
    autocomplete_fields = ("product", "tea_flavor_combination")
    fields = ("product", "category", "order", "tea_flavor_combination")
    ordering = ("order",)


class ProductTastingChartInline(admin.TabularInline):
    model = ProductTastingChart
    extra = 0
    autocomplete_fields = ("chart",)
    fields = ("chart", "order")
    ordering = ("order",)
    verbose_name = "Чарт (целиком, со всеми критериями)"
    verbose_name_plural = "Чарты (привязка целиком)"


class ProductTastingTasteCriteriaInline(admin.TabularInline):
    model = ProductTastingTasteCriteria
    extra = 0
    autocomplete_fields = ("criteria",)
    fields = ("criteria", "order", "for_tea_combination")
    ordering = ("order",)
    verbose_name = "Автономный критерий (без чарта)"
    verbose_name_plural = "Автономные критерии (без чарта)"


def _validate_photos_belong_to_product(photos, product_id, where=""):
    if photos and product_id:
        bad = [p.id for p in photos if p.product_id != product_id]
        if bad:
            suffix = f" ({where})" if where else ""
            raise ValidationError(f"Эти фото принадлежат другому продукту: {bad}{suffix}.")


def _scope_photos_to_product(db_field, request, kwargs):
    """Ограничивает виджет выбора `photos` фотками продукта редактируемого ProductTasting.
    Сам ProductTasting кладётся на request его админкой в get_form. На add-форме (продукт ещё
    не выбран) показываем пустой список — фото выбираются после сохранения позиции."""
    if db_field.name == "photos":
        obj = getattr(request, "_producttasting_obj", None)
        product_id = getattr(obj, "product_id", None)
        kwargs["queryset"] = ProductPhoto.objects.filter(product_id=product_id) if product_id else ProductPhoto.objects.none()


class ProductTastingTasteBlockInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        product_id = getattr(self.instance, "product_id", None)
        if not product_id:
            return
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            _validate_photos_belong_to_product(
                form.cleaned_data.get("photos"), product_id, where=f"блок «{form.cleaned_data.get('taste_block')}»"
            )


class ProductTastingTasteBlockInline(admin.TabularInline):
    model = ProductTastingTasteBlock
    formset = ProductTastingTasteBlockInlineFormSet
    extra = 0
    autocomplete_fields = ("taste_block",)
    fields = ("taste_block", "order", "show_tags", "photos")
    ordering = ("order",)
    verbose_name = "Раздел оценки"
    verbose_name_plural = "Разделы оценки (порядок в карточке)"

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        _scope_photos_to_product(db_field, request, kwargs)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class ProductTastingPhraseTemplateInline(admin.TabularInline):
    model = ProductTastingPhraseTemplate
    extra = 0
    autocomplete_fields = ("phrase_template",)
    fields = ("phrase_template", "order")
    ordering = ("order",)


class ProductTastingFreeTextPromptInline(admin.TabularInline):
    model = ProductTastingFreeTextPrompt
    extra = 0
    autocomplete_fields = ("free_text_prompt",)
    fields = ("free_text_prompt", "order")
    ordering = ("order",)


class TastingUserMarksInline(admin.TabularInline):
    model = ProductTastingUserMark
    fk_name = "tasting"
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("user", "product_tasting", "is_nominated", "podium_place", "updated_at")
    readonly_fields = ("user", "product_tasting", "is_nominated", "podium_place", "updated_at")
    ordering = ("podium_place", "-updated_at")
    verbose_name = "Метка пользователя"
    verbose_name_plural = "Номинации и подиумы (read-only)"

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "product_tasting__product")


@admin.register(Tasting)
class TastingAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "date", "products_count", "participants_count")
    list_filter = ("type", "date")
    search_fields = ("title", "id")
    date_hierarchy = "date"
    save_on_top = True
    inlines = [ProductTastingInline, TastingParticipationInline, TastingUserMarksInline]

    def get_queryset(self, request):
        from django.db.models import Count

        return (
            super()
            .get_queryset(request)
            .annotate(_products=Count("products", distinct=True), _participants=Count("participants", distinct=True))
        )

    @admin.display(description="Продуктов", ordering="_products")
    def products_count(self, obj):
        return obj._products

    @admin.display(description="Участников", ordering="_participants")
    def participants_count(self, obj):
        return obj._participants


class ProductTastingAdminForm(forms.ModelForm):
    class Meta:
        model = ProductTasting
        fields = "__all__"

    def clean_photos(self):
        photos = self.cleaned_data.get("photos")
        product = self.cleaned_data.get("product") or getattr(self.instance, "product", None)
        _validate_photos_belong_to_product(photos, getattr(product, "id", None))
        return photos


@admin.register(ProductTasting)
class ProductTastingAdmin(admin.ModelAdmin):
    form = ProductTastingAdminForm
    list_display = ("__str__", "category", "order", "charts_n", "criteria_n", "blocks_n", "phrases_n", "free_text_n")
    list_filter = ("tasting", "category")
    search_fields = ("product__name", "product__id", "tasting__title", "tasting__id", "category", "id")
    autocomplete_fields = ("product", "tasting", "tea_flavor_combination")
    filter_horizontal = ("photos",)
    list_select_related = ("tasting", "product")
    ordering = ("tasting", "order")
    save_on_top = True
    fields = ("tasting", "product", "category", "order", "tea_flavor_combination", "photos")
    inlines = [
        ProductTastingChartInline,
        ProductTastingTasteCriteriaInline,
        ProductTastingTasteBlockInline,
        ProductTastingPhraseTemplateInline,
        ProductTastingFreeTextPromptInline,
    ]

    def get_form(self, request, obj=None, **kwargs):
        # Кладём редактируемый ProductTasting на request, чтобы и его форма, и инлайны (блоки)
        # отфильтровали выбор photos по продукту этой позиции.
        request._producttasting_obj = obj
        return super().get_form(request, obj, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        _scope_photos_to_product(db_field, request, kwargs)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def get_queryset(self, request):
        from django.db.models import Count

        return (
            super()
            .get_queryset(request)
            .annotate(
                _charts=Count("producttastingchart", distinct=True),
                _criteria=Count("producttastingtastecriteria", distinct=True),
                _blocks=Count("producttastingtasteblock", distinct=True),
                _phrases=Count("producttastingphrasetemplate", distinct=True),
                _free_text=Count("producttastingfreetextprompt", distinct=True),
            )
        )

    @admin.display(description="Чартов", ordering="_charts")
    def charts_n(self, obj):
        return obj._charts

    @admin.display(description="Свободных", ordering="_free_text")
    def free_text_n(self, obj):
        return obj._free_text

    @admin.display(description="Автокритериев", ordering="_criteria")
    def criteria_n(self, obj):
        return obj._criteria

    @admin.display(description="Блоков", ordering="_blocks")
    def blocks_n(self, obj):
        return obj._blocks

    @admin.display(description="Фраз", ordering="_phrases")
    def phrases_n(self, obj):
        return obj._phrases


class ProductCriteriaReviewInline(admin.TabularInline):
    model = ProductCriteriaReview
    extra = 0
    autocomplete_fields = ("criteria",)
    fields = ("criteria", "x", "mark")


class PhraseTemplateReviewInline(admin.TabularInline):
    model = PhraseTemplateReview
    extra = 0
    autocomplete_fields = ("phrase_template",)
    fields = ("phrase_template", "answers")


class FreeTextPromptReviewInline(admin.TabularInline):
    model = FreeTextPromptReview
    extra = 0
    autocomplete_fields = ("free_text_prompt",)
    fields = ("free_text_prompt", "text")


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "product_tasting", "tasted", "is_bookmarked", "updated_at")
    list_editable = ("tasted", "is_bookmarked")
    list_filter = ("tasted", "is_bookmarked", "updated_at", "taste_tags")
    search_fields = (
        "id",
        "user__username",
        "user__phone",
        "user__first_name",
        "user__id",
        "product__name",
        "product__id",
        "product_tasting__tasting__title",
        "product_tasting__id",
    )
    autocomplete_fields = ("user", "product_tasting")
    filter_horizontal = ("taste_tags",)
    readonly_fields = ("product", "created_at", "updated_at")
    list_select_related = ("user", "product_tasting__tasting", "product")
    save_on_top = True
    inlines = [ProductCriteriaReviewInline, PhraseTemplateReviewInline, FreeTextPromptReviewInline]
    fieldsets = (
        (None, {"fields": ("user", "product_tasting", "product")}),
        ("Состояние", {"fields": ("tasted", "is_bookmarked")}),
        ("Отзыв", {"fields": ("global_comment", "self_comment", "composition", "taste_tags")}),
        ("Служебное", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(ProductTastingUserMark)
class ProductTastingUserMarkAdmin(admin.ModelAdmin):
    list_display = ("user", "product_display", "tasting", "is_nominated", "podium_place", "updated_at")
    list_editable = ("is_nominated", "podium_place")
    list_filter = ("tasting", "is_nominated", "podium_place")
    search_fields = (
        "id",
        "user__username",
        "user__phone",
        "user__first_name",
        "user__id",
        "product_tasting__product__name",
        "product_tasting__product__id",
        "product_tasting__id",
        "tasting__title",
        "tasting__id",
    )
    autocomplete_fields = ("user", "product_tasting", "tasting")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("user", "product_tasting", "tasting")}),
        ("Метки", {"fields": ("is_nominated", "podium_place")}),
        ("Служебное", {"fields": ("created_at", "updated_at")}),
    )
    ordering = ("tasting", "podium_place", "-updated_at")

    @admin.display(description="Продукт", ordering="product_tasting__product__name")
    def product_display(self, obj: ProductTastingUserMark):
        return obj.product_tasting.product

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "tasting", "product_tasting__product")


@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ("__str__", "show_share_link")
    fields = ("show_share_link", "share_text")

    def has_add_permission(self, request):
        return not Config.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
