import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models


class ProductTypeEnum(models.TextChoices):
    ICE_CREAM = "ice_cream", "Мороженое"
    TEA = "tea", "Чай"


class OrientationEnum(models.TextChoices):
    HORIZONTAL = "horizontal", "Горизонтальная"
    VERTICAL = "vertical", "Вертикальная"


class CircleChartLabelPlacementEnum(models.TextChoices):
    VERTICES = "vertices", "на вершинах"
    EDGES = "edges", "на рёбрах"


class ChartTypeEnum(models.TextChoices):
    CIRCLE = "circle", "Круговая"
    PLOT = "plot", "График"


class Line(models.Model):
    name = models.CharField(max_length=127)

    def __str__(self) -> str:
        return self.name


class TasteTags(models.Model):
    name = models.CharField(max_length=127)
    weight = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(-1), MaxValueValidator(1)],
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.weight:+.2f})"


class IceCreamLogo(models.Model):
    image = models.FileField(
        upload_to="ice_cream_logo/",
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "svg"])],
    )
    intro_name = models.CharField(max_length=127)
    text = models.CharField(max_length=127, null=True, blank=True, default=None)
    type = models.CharField(choices=ProductTypeEnum.choices, default=ProductTypeEnum.TEA)  # noqa

    def __str__(self) -> str:
        return self.intro_name or f"Логотип #{self.pk}"


class TasteBlock(models.Model):
    """Логический раздел карточки блюда («Оценка сухого листа», «Оценка заваренного чая», …).

    Группирует разнородные средства оценки (Chart-плоты/круги и автономные TasteCriteria).
    Порядок блоков задаётся per-tasting через through TastingTasteBlock.
    """

    name = models.CharField(max_length=127)
    description = models.TextField(blank=True, null=True)

    def __str__(self) -> str:
        return self.name


class Chart(models.Model):
    name = models.CharField(max_length=127)
    description = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=7, blank=True, null=True)  # Hex color code
    chart_type = models.CharField(choices=ChartTypeEnum.choices, default=ChartTypeEnum.CIRCLE)  # noqa
    taste_block = models.ForeignKey(
        TasteBlock, on_delete=models.SET_NULL, null=True, blank=True, default=None, related_name="charts"
    )
    label_placement = models.CharField(
        choices=CircleChartLabelPlacementEnum.choices, default=CircleChartLabelPlacementEnum.EDGES
    )  # noqa

    # plot-специфика (chart_type == "plot"): на круговом чарте остаются пустыми.
    # x_axis / y_axis — упорядоченные списки делений {value, label}, как TasteCriteria.grade.
    # Y-шкала на Plot общая для всех его критериев — поэтому живёт здесь, а не на критерии.
    x_axis = models.JSONField(blank=True, default=list)
    y_axis = models.JSONField(blank=True, default=list)
    x_axis_name = models.CharField(max_length=127, blank=True, null=True, default=None)
    y_axis_name = models.CharField(max_length=127, blank=True, null=True, default=None)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class TasteCriteria(models.Model):
    name = models.CharField(max_length=127)
    grade = models.JSONField(blank=True, default=list)
    description = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    orientation = models.CharField(  # noqa
        choices=OrientationEnum.choices,
        null=True,
        blank=True,
        default=None,
    )
    chart = models.ForeignKey(Chart, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    # Раздел карточки, к которому относится автономный критерий. Для критериев с привязкой к chart
    # игнорируется (блок берётся у самого chart) — в API у таких критериев taste_block не отдаём.
    taste_block = models.ForeignKey(
        TasteBlock, on_delete=models.SET_NULL, null=True, blank=True, default=None, related_name="criterias"
    )

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(chart__isnull=False, orientation__isnull=False),
                name="tastecriteria_chart_or_orientation_not_both",
            ),
        ]

    def __str__(self) -> str:
        return self.name


PHRASE_BLANK_TOKEN = "{blank}"


class PhraseTemplate(models.Model):
    """Заготовленная фраза с пропусками («cloze»). `template` хранит текст с токенами {blank}
    на месте пропусков, напр.: «Этот чай напомнил мне {blank}, а также {blank}.». Гость заполняет
    пропуски на фронте; ответы (по одному на пропуск, по порядку) хранятся в PhraseTemplateReview."""

    name = models.CharField(max_length=127, blank=True, null=True, default=None)
    template = models.TextField(
        help_text="Текст с токенами {blank} на месте пропусков, напр.: "
        "«Этот чай напомнил мне {blank}, а также {blank}.»"
    )
    order = models.PositiveIntegerField(default=0)
    show_toggle_list = models.BooleanField(default=True)
    taste_block = models.ForeignKey(
        TasteBlock, on_delete=models.SET_NULL, null=True, blank=True, default=None, related_name="phrase_templates"
    )

    class Meta:
        ordering = ["order", "id"]

    @property
    def blanks_count(self) -> int:
        return self.template.count(PHRASE_BLANK_TOKEN)

    @property
    def segments(self) -> list[str]:
        """Статические куски текста вокруг пропусков: фронт рисует segment, input, segment, …
        Их на единицу больше, чем пропусков."""
        return self.template.split(PHRASE_BLANK_TOKEN)

    def __str__(self) -> str:
        if self.name:
            return self.name
        return self.template[:40] + ("…" if len(self.template) > 40 else "")


class FreeTextPrompt(models.Model):
    """Простой промпт для свободного ввода: name + description (что написать), а сам текст гость
    вводит/редактирует в отзыве (FreeTextPromptReview.text)."""

    name = models.CharField(max_length=127)
    description = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    taste_block = models.ForeignKey(
        TasteBlock, on_delete=models.SET_NULL, null=True, blank=True, default=None, related_name="free_text_prompts"
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    # common
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=ProductTypeEnum.choices)  # noqa
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    image = models.FileField(
        upload_to="products/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "svg"])],
    )
    result_phrase = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=7, blank=True, null=True)  # Hex color code

    taste_tags = models.ManyToManyField(TasteTags, related_name="products", blank=True)
    tasters = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ProductReview",
        related_name="tasted_products",
        blank=True,
    )

    # tea
    tea_nickname = models.CharField(max_length=127, null=True, blank=True, default=None)
    tea_sort = models.CharField(max_length=127, null=True, blank=True, default=None)
    tea_index = models.CharField(max_length=127, null=True, blank=True, default=None)
    tea_price = models.FloatField(null=True, blank=True, default=None)
    tea_measure_unit = models.CharField(max_length=127, null=True, blank=True, default="грамм")
    tea_geography = models.CharField(max_length=127, null=True, blank=True, default=None)
    tea_plucking_season = models.CharField(max_length=127, null=True, blank=True, default=None)
    tea_rubrucator = models.CharField(max_length=127, null=True, blank=True, default=None)
    tea_cultivar = models.CharField(max_length=127, null=True, blank=True, default=None)
    tea_altitude = models.CharField(max_length=127, null=True, blank=True, default=None)
    tea_color_type_name = models.CharField(max_length=127, null=True, blank=True, default=None)

    # ice cream
    number = models.IntegerField(null=True, blank=True, default=None)
    line = models.ForeignKey(Line, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    interesting_fact = models.TextField(blank=True, null=True)
    composition = models.JSONField(blank=True, null=True, default=list)
    logos = models.ManyToManyField(IceCreamLogo, related_name="products", blank=True, through="ProductIceCreamLogo")

    def __str__(self) -> str:
        return f"{self.get_type_display()} — {self.name}"


class ProductIceCreamLogo(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    logo = models.ForeignKey(IceCreamLogo, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.product} — {self.logo}"


class ProductPhoto(models.Model):
    """Произвольное фото продукта. В сам Product можно загрузить сколько угодно фото; затем
    нужные выбираются per-ProductTasting и/или per-ProductTastingTasteBlock. `name` — служебное,
    на фронт не отдаётся."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="photos")
    image = models.FileField(
        upload_to="product_photos/",
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "svg"])],
    )
    name = models.CharField(max_length=200, blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        label = self.name or f"#{self.pk}"
        return f"{self.product.name} — {label}"


class Tasting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    result_description = models.TextField(blank=True, null=True)
    type = models.CharField(
        choices=ProductTypeEnum.choices,  # noqa
        default=ProductTypeEnum.ICE_CREAM,
    )
    date = models.DateTimeField()
    # Показывать ли на фронте в карточке блюда кнопку «номинировать в кандидаты на пьедестал».
    show_podium_candidates = models.BooleanField(default=True)
    products = models.ManyToManyField(Product, through="ProductTasting", related_name="tastings", blank=True)
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="TastingParticipation",
        related_name="tastings",
        blank=True,
    )

    def __str__(self) -> str:
        return self.title


class ProductTasting(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    tasting = models.ForeignKey(Tasting, on_delete=models.CASCADE)
    category = models.CharField(max_length=127, blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    tea_flavor_combination = models.ManyToManyField(
        Product,
        related_name="+",
        blank=True,
    )
    # Конфиг оценки живёт на уровне (продукт, дегустация): что и как оценивать может отличаться
    # от дегустации к дегустации. Сам Product — чисто информационная сущность.
    taste_criteria = models.ManyToManyField(
        TasteCriteria, through="ProductTastingTasteCriteria", related_name="product_tastings", blank=True
    )
    taste_blocks = models.ManyToManyField(
        TasteBlock, through="ProductTastingTasteBlock", related_name="product_tastings", blank=True
    )
    phrase_templates = models.ManyToManyField(
        PhraseTemplate, through="ProductTastingPhraseTemplate", related_name="product_tastings", blank=True
    )
    # Чарт можно привязать целиком — в карточку едут все его TasteCriteria. Это удобнее, чем
    # перечислять критерии чарта по одному. Автономные (chart IS NULL) критерии — через taste_criteria.
    charts = models.ManyToManyField(Chart, through="ProductTastingChart", related_name="product_tastings", blank=True)
    free_text_prompts = models.ManyToManyField(
        FreeTextPrompt, through="ProductTastingFreeTextPrompt", related_name="product_tastings", blank=True
    )
    # Произвольный набор фото продукта, выбранных для карточки в этой дегустации. Несвязное
    # подмножество ProductPhoto этого же продукта (с per-block выбором не пересекается логически).
    photos = models.ManyToManyField(ProductPhoto, related_name="product_tastings", blank=True)

    def __str__(self) -> str:
        return f"{self.tasting} — {self.product}"


class ProductTastingTasteCriteria(models.Model):
    product_tasting = models.ForeignKey(ProductTasting, on_delete=models.CASCADE)
    criteria = models.ForeignKey(TasteCriteria, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    for_tea_combination = models.BooleanField(default=False)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product_tasting", "criteria"], name="uniq_product_tasting_criteria"),
        ]

    def __str__(self) -> str:
        return f"{self.product_tasting} — {self.criteria}"


class ProductTastingTasteBlock(models.Model):
    product_tasting = models.ForeignKey(ProductTasting, on_delete=models.CASCADE)
    taste_block = models.ForeignKey(TasteBlock, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    show_tags = models.BooleanField(default=False, verbose_name="Отображать теги в данном блоке")
    # Произвольный набор фото продукта для этого раздела карточки. Независим от ProductTasting.photos
    # и от других блоков — наборы могут пересекаться или нет.
    photos = models.ManyToManyField(ProductPhoto, related_name="taste_blocks", blank=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product_tasting", "taste_block"], name="uniq_product_tasting_taste_block"),
        ]

    def __str__(self) -> str:
        return f"{self.product_tasting} — {self.taste_block}"


class ProductTastingPhraseTemplate(models.Model):
    product_tasting = models.ForeignKey(ProductTasting, on_delete=models.CASCADE)
    phrase_template = models.ForeignKey(PhraseTemplate, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product_tasting", "phrase_template"], name="uniq_product_tasting_phrase_template"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_tasting} — {self.phrase_template}"


class ProductTastingChart(models.Model):
    product_tasting = models.ForeignKey(ProductTasting, on_delete=models.CASCADE)
    chart = models.ForeignKey(Chart, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product_tasting", "chart"], name="uniq_product_tasting_chart"),
        ]

    def __str__(self) -> str:
        return f"{self.product_tasting} — {self.chart}"


class ProductTastingFreeTextPrompt(models.Model):
    product_tasting = models.ForeignKey(ProductTasting, on_delete=models.CASCADE)
    free_text_prompt = models.ForeignKey(FreeTextPrompt, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product_tasting", "free_text_prompt"], name="uniq_product_tasting_free_text_prompt"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_tasting} — {self.free_text_prompt}"


class TastingParticipation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tasting = models.ForeignKey(Tasting, on_delete=models.CASCADE, related_name="participations")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tasting_participations",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tasting", "user"], name="uniq_tasting_user"),
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.tasting}"


class ProductReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    # Оценка привязана к (гость, продукт-в-дегустации). product оставляем денормализацией
    # (заполняется в save из product_tasting) — упрощает фильтры по продукту и M2M Product.tasters.
    product_tasting = models.ForeignKey(
        ProductTasting,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    global_comment = models.TextField(blank=True, null=True)
    self_comment = models.TextField(blank=True, null=True)
    tasted = models.BooleanField(default=False)
    is_bookmarked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    composition = models.JSONField(blank=True, default=list)
    taste_criteria = models.ManyToManyField(
        TasteCriteria,
        through="ProductCriteriaReview",
        related_name="reviews",
        blank=True,
    )
    taste_tags = models.ManyToManyField(TasteTags, related_name="reviews", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "product_tasting"], name="uniq_user_product_tasting_review"),
        ]

    def save(self, *args, **kwargs):
        if self.product_tasting_id and not self.product_id:
            self.product_id = self.product_tasting.product_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.user} → {self.product_tasting}"


class ProductCriteriaReview(models.Model):
    product_review = models.ForeignKey(ProductReview, on_delete=models.CASCADE, related_name="criteria_reviews")
    criteria = models.ForeignKey(TasteCriteria, on_delete=models.CASCADE, related_name="criteria")
    # mark = Y-координата точки (значение по шкале критерия / y_axis чарта).
    mark = models.IntegerField()
    # x — координата на оси X для критериев Plot-чарта. NULL для обычных/круговых критериев,
    # у которых оценка одномерна (одна строка на (review, criteria)). У Plot-критерия точек
    # столько, сколько делений на оси X: одна строка на (review, criteria, x).
    x = models.PositiveSmallIntegerField(null=True, blank=True, default=None)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product_review", "criteria"],
                condition=models.Q(x__isnull=True),
                name="uniq_criteria_review_no_x",
            ),
            models.UniqueConstraint(
                fields=["product_review", "criteria", "x"],
                condition=models.Q(x__isnull=False),
                name="uniq_criteria_review_per_x",
            ),
        ]

    def __str__(self) -> str:
        suffix = f" @x={self.x}" if self.x is not None else ""
        return f"{self.product_review} — {self.criteria}: {self.mark}{suffix}"


class PhraseTemplateReview(models.Model):
    product_review = models.ForeignKey(ProductReview, on_delete=models.CASCADE, related_name="phrase_reviews")
    phrase_template = models.ForeignKey(PhraseTemplate, on_delete=models.CASCADE, related_name="+")
    # answers — список строк по одному значению на каждый пропуск шаблона, по порядку.
    answers = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product_review", "phrase_template"], name="uniq_phrase_template_review"),
        ]

    def __str__(self) -> str:
        return f"{self.product_review} — {self.phrase_template}"


class FreeTextPromptReview(models.Model):
    product_review = models.ForeignKey(ProductReview, on_delete=models.CASCADE, related_name="free_text_reviews")
    free_text_prompt = models.ForeignKey(FreeTextPrompt, on_delete=models.CASCADE, related_name="+")
    text = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product_review", "free_text_prompt"], name="uniq_free_text_prompt_review"),
        ]

    def __str__(self) -> str:
        return f"{self.product_review} — {self.free_text_prompt}"


class ProductTastingUserMark(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_tasting_marks",
    )
    product_tasting = models.ForeignKey(
        ProductTasting,
        on_delete=models.CASCADE,
        related_name="user_marks",
    )
    tasting = models.ForeignKey(
        Tasting,
        on_delete=models.CASCADE,
        related_name="user_marks",
    )
    is_nominated = models.BooleanField(default=False)
    # Место в рейтинге блюд гостя для этой дегустации (1 = лучшее). Раньше ограничивалось топ-3,
    # теперь можно отранжировать все блюда (1..N) через podium-эндпоинт. В результат как «подиум»
    # всё равно идут места 1..3. NULL — блюдо не отранжировано.
    podium_place = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "product_tasting"], name="uniq_user_product_tasting_mark"),
            models.UniqueConstraint(
                fields=["user", "tasting", "podium_place"],
                condition=models.Q(podium_place__isnull=False),
                name="uniq_user_tasting_podium_place",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.product_tasting_id and not self.tasting_id:
            self.tasting_id = self.product_tasting.tasting_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.user} → {self.product_tasting}"


class Config(models.Model):
    show_share_link = models.BooleanField(default=False)
    share_text = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Конфиг"
        verbose_name_plural = "Конфиг"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "Config":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return "Конфиг"
