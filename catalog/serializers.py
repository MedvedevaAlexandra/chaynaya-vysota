from decimal import ROUND_HALF_UP, Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    ChartTypeEnum,
    Config,
    IceCreamLogo,
    TasteTags,
    Product,
    Tasting,
    TastingParticipation,
)

GRADE_SCHEMA = {
    "type": "array",
    "description": (
        "Шкала оценки как упорядоченный список пар {value, label}. "
        "Список — чтобы сохранять порядок отображения в админке/фронте и допускать дубли "
        "value (две разные подписи на одно и то же числовое значение)."
    ),
    "items": {
        "type": "object",
        "properties": {
            "value": {"type": "integer", "description": "Числовое значение оценки."},
            "label": {"type": "string", "description": "Человекочитаемая подпись."},
        },
        "required": ["value", "label"],
    },
}

_TASTE_CRITERIA_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "description": {"type": "string", "nullable": True},
        "grade": GRADE_SCHEMA,
        "orientation": {
            "type": "string",
            "enum": ["horizontal", "vertical"],
            "nullable": True,
            "description": (
                "Ориентация отрисовки шкалы критерия. null, когда критерий привязан к CircleChart "
                "(там ориентация задаётся самим чартом). DB-инвариант: одновременно chart и orientation не задаются."
            ),
        },
        "for_tea_combination": {
            "type": "boolean",
            "description": "Признак с through-модели ProductTasteCriteria: применяется ли этот критерий "
            "к оценке сочетания с чаем для данного продукта.",
        },
        "user_grade_review": {
            "type": "integer",
            "nullable": True,
            "description": "Оценка текущего пользователя по критерию; null, если он не оценивал.",
        },
    },
    "required": [
        "id",
        "name",
        "description",
        "grade",
        "orientation",
        "for_tea_combination",
        "user_grade_review",
    ],
}

_TASTE_BLOCK_PROP = {
    "type": "integer",
    "nullable": True,
    "description": (
        "id TasteBlock — раздел карточки, к которому относится элемент. Есть только у автономных "
        "критериев и у чартов/плотов; у критериев внутри chart/plot не отдаётся (блок берётся у самого "
        "chart/plot). null, если элемент не отнесён к блоку."
    ),
}

_ORDER_PROP = {
    "type": "integer",
    "description": (
        "Сквозной порядок элемента ВНУТРИ блока (`ProductTasting<...>.order`). Шкала общая для всех "
        "типов средств оценки (критерии/чарты/плоты/фразы/свободный текст) — фронт мёржит их в один "
        "список по этому `order` в пределах одного `taste_block`."
    ),
}

_STANDALONE_TASTE_CRITERIA_ITEM_SCHEMA = {
    "type": "object",
    "properties": {**_TASTE_CRITERIA_ITEM_SCHEMA["properties"], "taste_block": _TASTE_BLOCK_PROP, "order": _ORDER_PROP},
    "required": _TASTE_CRITERIA_ITEM_SCHEMA["required"] + ["taste_block", "order"],
}

TASTE_CRITERIA_SCHEMA = {
    "type": "array",
    "description": "Автономные критерии оценки, НЕ привязанные к Chart. Критерии чартов — в `charts`/`plots`.",
    "items": _STANDALONE_TASTE_CRITERIA_ITEM_SCHEMA,
}

PHOTOS_SCHEMA = {
    "type": "array",
    "description": "Выбранные фото продукта (URL + id). Имя фото служебное и не отдаётся.",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "image": {"type": "string", "format": "uri"},
        },
        "required": ["id", "image"],
    },
}

TASTE_BLOCKS_SCHEMA = {
    "type": "array",
    "description": (
        "Разделы карточки блюда в порядке для текущей дегустации (TastingTasteBlock.order). "
        "Фронт рендерит секции по этому списку, раскладывая чарты/плоты/критерии по их taste_block."
    ),
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "show_tags": {"type": "boolean", "description": "Отображать ли блок тегов внутри этого раздела."},
            "photos": PHOTOS_SCHEMA,
        },
        "required": ["id", "name", "show_tags", "photos"],
    },
}

CHARTS_SCHEMA = {
    "type": "array",
    "description": (
        "Группы критериев, объединённых одним Chart типа `circle`. Появляются здесь, если у "
        "TasteCriteria.chart задан круговой чарт. Plot-чарты — в поле `plots`. Те же критерии в "
        "`taste_criteria` не дублируются."
    ),
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "description": {"type": "string", "nullable": True},
            "color": {"type": "string", "nullable": True, "description": "Hex-цвет (#rrggbb) для UI."},
            "label_placement": {
                "type": "string",
                "enum": ["vertices", "edges"],
                "description": "Где рендерить подписи критериев чарта: на вершинах многоугольника или на рёбрах.",
            },
            "taste_block": _TASTE_BLOCK_PROP,
            "order": _ORDER_PROP,
            "criterias": {"type": "array", "items": _TASTE_CRITERIA_ITEM_SCHEMA},
        },
        "required": ["id", "name", "description", "color", "label_placement", "taste_block", "order", "criterias"],
    },
}

_PLOT_POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "x": {"type": "integer", "description": "Деление на оси X чарта (из Chart.x_axis)."},
        "mark": {"type": "integer", "description": "Значение по оси Y (из Chart.y_axis) — Y-координата точки."},
    },
    "required": ["x", "mark"],
}

_PLOT_CRITERIA_ITEM_SCHEMA = {
    "type": "object",
    "description": "Критерий внутри Plot-чарта — отдельная серия (линия). Y-шкала общая на весь чарт (Chart.y_axis).",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "description": {"type": "string", "nullable": True},
        "for_tea_combination": {
            "type": "boolean",
            "description": "Признак с through-модели ProductTasteCriteria: критерий про сочетание с чаем.",
        },
        "user_grade_review": {
            "type": "array",
            "items": _PLOT_POINT_SCHEMA,
            "description": "Точки текущего пользователя по этой серии: по одной на каждое выставленное "
            "деление X. Пустой список, если пользователь ничего не отмечал.",
        },
    },
    "required": ["id", "name", "description", "for_tea_combination", "user_grade_review"],
}

PLOTS_SCHEMA = {
    "type": "array",
    "description": (
        "Группы критериев, объединённых одним Chart типа `plot`. Каждый критерий — серия по оси Y; "
        "ось X (Chart.x_axis) общая. Оценка двухкоординатная: в каждой точке (x, mark). Критерии "
        "Plot-чартов не попадают в `taste_criteria`/`charts`."
    ),
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "description": {"type": "string", "nullable": True},
            "color": {"type": "string", "nullable": True, "description": "Hex-цвет (#rrggbb) для UI."},
            "x_axis": GRADE_SCHEMA,
            "y_axis": GRADE_SCHEMA,
            "x_axis_name": {"type": "string", "nullable": True, "description": "Заголовок оси X."},
            "y_axis_name": {"type": "string", "nullable": True, "description": "Заголовок оси Y."},
            "taste_block": _TASTE_BLOCK_PROP,
            "order": _ORDER_PROP,
            "criterias": {"type": "array", "items": _PLOT_CRITERIA_ITEM_SCHEMA},
        },
        "required": [
            "id",
            "name",
            "description",
            "color",
            "x_axis",
            "y_axis",
            "x_axis_name",
            "y_axis_name",
            "taste_block",
            "order",
            "criterias",
        ],
    },
}

PHRASES_SCHEMA = {
    "type": "array",
    "description": (
        "Заготовленные фразы с пропусками (PhraseTemplate), сконфигурированные для этого продукта в "
        "этой дегустации. Фронт рисует `segments` со вводами между ними (`blanks_count` пропусков) и "
        "отправляет заполнения через `phrase_answers` в review."
    ),
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string", "nullable": True, "description": "Служебное название шаблона."},
            "template": {"type": "string", "description": "Исходный текст с токенами {blank} на месте пропусков."},
            "segments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Статические куски текста вокруг пропусков (на 1 больше, чем пропусков).",
            },
            "blanks_count": {"type": "integer", "description": "Сколько пропусков нужно заполнить."},
            "taste_block": _TASTE_BLOCK_PROP,
            "order": _ORDER_PROP,
            "user_answers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ответы текущего пользователя по пропускам (по порядку). Пустой список, если не заполнял.",
            },
        },
        "required": ["id", "name", "template", "segments", "blanks_count", "taste_block", "order", "user_answers"],
    },
}

FREE_TEXT_PROMPTS_SCHEMA = {
    "type": "array",
    "description": (
        "Промпты для свободного ввода (FreeTextPrompt), сконфигурированные для этого продукта в этой "
        "дегустации. Гость пишет произвольный текст; отправляется через `free_text_answers` в review."
    ),
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "description": {"type": "string", "nullable": True},
            "taste_block": _TASTE_BLOCK_PROP,
            "order": _ORDER_PROP,
            "user_text": {
                "type": "string",
                "description": "Текст текущего пользователя. Пустая строка, если он ничего не вводил.",
            },
        },
        "required": ["id", "name", "description", "taste_block", "order", "user_text"],
    },
}

USER_COMPOSITION_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
    "nullable": True,
    "description": "Личный состав текущего пользователя; null, если он ещё не оставлял отзыв.",
}

TEA_FLAVOR_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "name": {"type": "string"},
            "logo": {
                "type": "string",
                "format": "uri",
                "nullable": True,
                "description": "URL первого логотипа связного продукта; null, если у продукта нет логотипов.",
            },
        },
        "required": ["id", "name", "logo"],
    },
    "description": (
        "Сочетания вкусов для данной дегустации: список связанных Product "
        "(M2M на ProductTasting.tea_flavor_combination), отдаётся как {id, name, logo}."
    ),
}

TASTE_TAGS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "weight": {"type": "number", "minimum": -1, "maximum": 1},
            "marked": {
                "type": "boolean",
                "description": "true, если текущий пользователь выбрал этот тег.",
            },
        },
        "required": ["id", "name", "weight", "marked"],
    },
}

TASTING_MARKS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "tasting_id": {"type": "string", "format": "uuid"},
            "tasting_title": {"type": "string"},
            "is_nominated": {"type": "boolean"},
            "podium_place": {"type": "integer", "nullable": True, "minimum": 1, "maximum": 3},
        },
        "required": ["tasting_id", "tasting_title", "is_nominated", "podium_place"],
    },
    "description": (
        "Контекстные метки текущего пользователя для продукта по конкретным дегустациям "
        "(номинация, место в топ-3). Пустой список для анонима и продукта вне дегустаций."
    ),
}


TOTAL_SCORE_SCHEMA = {
    "type": "integer",
    "nullable": True,
    "description": (
        "Суммарный балл текущего пользователя: сумма user_grade_review по критериям + "
        "сумма weight выбранных тегов; округляется до целого по правилам арифметического "
        "округления (HALF_UP). null — продукт не попробован; 0 — попробован, но ничего не оценено."
    ),
}


class IceCreamLogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = IceCreamLogo
        fields = ["id", "image", "text"]


class ProductSerializer(serializers.ModelSerializer):
    """Чисто информационная карточка продукта. Без оценочной части — критерии/чарты/оценки
    живут на уровне дегустации и отдаются в ProductInTastingSerializer."""

    line = serializers.SerializerMethodField()
    logos = IceCreamLogoSerializer(many=True, read_only=True)
    composition = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "type",
            "name",
            "number",
            "line",
            "description",
            "interesting_fact",
            "composition",
            "image",
            "logos",
            "color",
            "result_phrase",
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
        ]

    def get_line(self, obj: Product) -> str | None:
        return obj.line.name if obj.line else None


class PlotMarkSerializer(serializers.Serializer):
    criteria = serializers.IntegerField(help_text="id TasteCriteria, привязанного к Plot-чарту.")
    x = serializers.IntegerField(help_text="Деление оси X чарта (значение из Chart.x_axis).")
    mark = serializers.IntegerField(help_text="Значение оси Y (из Chart.y_axis) — Y-координата точки.")


class PhraseAnswerSerializer(serializers.Serializer):
    phrase = serializers.IntegerField(
        help_text="id PhraseTemplate, сконфигурированного для этого продукта в дегустации."
    )
    answers = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        help_text="По одному значению на каждый пропуск шаблона, по порядку. Длина должна совпадать с blanks_count.",
    )


class FreeTextAnswerSerializer(serializers.Serializer):
    prompt = serializers.IntegerField(
        help_text="id FreeTextPrompt, сконфигурированного для этого продукта в дегустации."
    )
    text = serializers.CharField(allow_blank=True, help_text="Произвольный текст пользователя.")


class ProductReviewWriteSerializer(serializers.Serializer):
    global_comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    self_comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    composition = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False,
        help_text="Личный состав, как его воспринял пользователь.",
    )
    criteria_marks = serializers.DictField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Одномерные оценки (taste_criteria / circle-чарты): ключ — id TasteCriteria (строка), "
        "значение — целая оценка. Для Plot-критериев используйте plot_marks.",
    )
    plot_marks = PlotMarkSerializer(
        many=True,
        required=False,
        help_text="Точки для Plot-критериев: список {criteria, x, mark}. criteria — id TasteCriteria, "
        "привязанного к Plot-чарту; x — деление оси X чарта; mark — значение оси Y.",
    )
    phrase_answers = PhraseAnswerSerializer(
        many=True,
        required=False,
        help_text="Заполнения фраз-шаблонов: список {phrase, answers}. phrase — id PhraseTemplate; "
        "answers — значения по пропускам по порядку (длина = blanks_count).",
    )
    free_text_answers = FreeTextAnswerSerializer(
        many=True,
        required=False,
        help_text="Свободный текст по промптам: список {prompt, text}. prompt — id FreeTextPrompt; "
        "text — произвольная строка (пустая строка очищает).",
    )
    taste_tags = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Id вкусовых тегов (IceCreamTasteTags), которые пользователь хочет отметить.",
    )
    tasted = serializers.BooleanField(
        required=False,
        help_text="Явный флаг «попробовал». Авто-выставляется в true при любой осмысленной полезной нагрузке.",
    )
    is_bookmarked = serializers.BooleanField(
        required=False,
        help_text="Закладка/избранное на блюдо. Независима от tasted.",
    )


class ProductInTastingSerializer(ProductSerializer):
    """Карточка продукта в контексте конкретной дегустации: информация + оценочная часть
    (критерии/чарты/плоты/блоки и личные оценки текущего пользователя по этому ProductTasting).

    Весь контекст вьюшка кладёт в obj.__dict__: `_taste_criteria_rows` (строки
    ProductTastingTasteCriteria с select_related criteria/chart), `_taste_blocks`,
    `_tea_flavor_combination`, `_category`, `_current_tasting_mark`, `_current_review`."""

    taste_criteria = serializers.SerializerMethodField()
    charts = serializers.SerializerMethodField()
    plots = serializers.SerializerMethodField()
    phrases = serializers.SerializerMethodField()
    free_text_prompts = serializers.SerializerMethodField()
    taste_blocks = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    taste_tags = serializers.SerializerMethodField()
    tasted = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()
    is_reviewed = serializers.SerializerMethodField()
    self_comment = serializers.SerializerMethodField()
    global_comment = serializers.SerializerMethodField()
    user_composition = serializers.SerializerMethodField()
    total_score = serializers.SerializerMethodField()
    tea_flavor_combination = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    is_nominated = serializers.SerializerMethodField()
    podium_place = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + [
            "taste_criteria",
            "charts",
            "plots",
            "phrases",
            "free_text_prompts",
            "taste_blocks",
            "photos",
            "taste_tags",
            "tasted",
            "is_bookmarked",
            "is_reviewed",
            "self_comment",
            "global_comment",
            "user_composition",
            "total_score",
            "tea_flavor_combination",
            "category",
            "is_nominated",
            "podium_place",
        ]

    # --- личный отзыв (ProductReview для текущего product_tasting) ---

    @staticmethod
    def _review(obj: Product):
        return obj.__dict__.get("_current_review")

    def get_tasted(self, obj: Product) -> bool:
        review = self._review(obj)
        return bool(review and review.tasted)

    def get_is_bookmarked(self, obj: Product) -> bool:
        review = self._review(obj)
        return bool(review and review.is_bookmarked)

    def get_is_reviewed(self, obj: Product) -> bool:
        review = self._review(obj)
        if review is not None:
            if review.global_comment or review.self_comment:
                return True
            if review.composition:
                return True
            if list(review.criteria_reviews.all()):
                return True
            if list(review.taste_tags.all()):
                return True
        mark = obj.__dict__.get("_current_tasting_mark")
        return bool(mark and mark.is_nominated)

    def get_self_comment(self, obj: Product) -> str | None:
        review = self._review(obj)
        return review.self_comment if review else None

    def get_global_comment(self, obj: Product) -> str | None:
        review = self._review(obj)
        return review.global_comment if review else None

    @extend_schema_field(USER_COMPOSITION_SCHEMA)
    def get_user_composition(self, obj: Product):
        review = self._review(obj)
        return review.composition if review else None

    @extend_schema_field(TASTE_TAGS_SCHEMA)
    def get_taste_tags(self, obj: Product) -> list[dict]:
        review = self._review(obj)
        marked_ids: set[int] = set()
        if review:
            marked_ids = {t.pk for t in review.taste_tags.all()}
        return [
            {"id": t.pk, "name": t.name, "weight": t.weight, "marked": t.pk in marked_ids} for t in obj.taste_tags.all()
        ]

    @extend_schema_field(TOTAL_SCORE_SCHEMA)
    def get_total_score(self, obj: Product) -> int | None:
        review = self._review(obj)
        if not review:
            return None
        marks_sum = sum(cr.mark for cr in review.criteria_reviews.all())
        weights_sum = sum(t.weight for t in review.taste_tags.all())
        total = Decimal(str(marks_sum + weights_sum))
        return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    # --- конфиг оценки (ProductTastingTasteCriteria для текущего product_tasting) ---

    @staticmethod
    def _criteria_rows(obj: Product):
        return obj.__dict__.get("_taste_criteria_rows", [])

    def _criteria_marks(self, obj: Product) -> dict[int, int]:
        review = self._review(obj)
        if not review:
            return {}
        # Одномерные оценки (taste_criteria / circle-чарты) живут в строках с x IS NULL.
        return {cr.criteria_id: cr.mark for cr in review.criteria_reviews.all() if cr.x is None}

    def _plot_points(self, obj: Product) -> dict[int, list[dict]]:
        """{criteria_id: [{x, mark}, ...]} — точки Plot-критериев (строки с заполненным x), отсортированы по x."""
        review = self._review(obj)
        if not review:
            return {}
        points: dict[int, list[dict]] = {}
        for cr in review.criteria_reviews.all():
            if cr.x is None:
                continue
            points.setdefault(cr.criteria_id, []).append({"x": cr.x, "mark": cr.mark})
        for rows in points.values():
            rows.sort(key=lambda p: p["x"])
        return points

    @staticmethod
    def _criteria_item(row, marks: dict[int, int]) -> dict:
        return {
            "id": row.criteria_id,
            "name": row.criteria.name,
            "description": row.criteria.description,
            "grade": row.criteria.grade,
            "orientation": row.criteria.orientation,
            "for_tea_combination": row.for_tea_combination,
            "user_grade_review": marks.get(row.criteria_id),
        }

    @extend_schema_field(TASTE_CRITERIA_SCHEMA)
    def get_taste_criteria(self, obj: Product) -> list[dict]:
        marks = self._criteria_marks(obj)
        out = []
        for row in self._criteria_rows(obj):
            if row.criteria.chart_id is not None:
                continue
            item = self._criteria_item(row, marks)
            item["taste_block"] = row.criteria.taste_block_id
            item["order"] = row.order
            out.append(item)
        return out

    @staticmethod
    def _chart_criteria_item(criteria, marks: dict[int, int]) -> dict:
        # Критерий ЯВНО привязанного чарта приходит целиком из Chart, per-tasting through нет:
        # for_tea_combination всегда False (match-критерий держим автономным).
        return {
            "id": criteria.id,
            "name": criteria.name,
            "description": criteria.description,
            "grade": criteria.grade,
            "orientation": criteria.orientation,
            "for_tea_combination": False,
            "user_grade_review": marks.get(criteria.id),
        }

    @staticmethod
    def _plot_series_item(criteria, points: dict[int, list[dict]]) -> dict:
        return {
            "id": criteria.id,
            "name": criteria.name,
            "description": criteria.description,
            "for_tea_combination": False,
            "user_grade_review": points.get(criteria.id, []),
        }

    @staticmethod
    def _plot_series_item_from_row(row, points: dict[int, list[dict]]) -> dict:
        return {
            "id": row.criteria_id,
            "name": row.criteria.name,
            "description": row.criteria.description,
            "for_tea_combination": row.for_tea_combination,
            "user_grade_review": points.get(row.criteria_id, []),
        }

    def _collect_chart_entries(self, obj: Product, *, is_plot: bool, build_explicit, build_implicit) -> list[dict]:
        """Собирает чарты заданного типа из ДВУХ источников:
        - ЯВНАЯ привязка `ProductTasting.charts` (`_chart_rows`) → чарт со ВСЕМИ его критериями, `order`
          из `ProductTastingChart.order`;
        - НЕЯВНО через критерии (`_criteria_rows`, у которых `criteria.chart` задан, но чарт НЕ привязан
          явно) → чарт только с критериями, реально входящими в этот ProductTasting (подмножество),
          `order` = минимальный `order` среди этих критериев.
        Явная привязка имеет приоритет: если чарт привязан, его through-критерии игнорируются.
        Возвращает entries [{chart, order, criterias}], отсортированные по (order, chart.id)."""
        entries: dict[int, dict] = {}
        explicit_ids: set[int] = set()

        for row in obj.__dict__.get("_chart_rows", []):
            chart = row.chart
            if (chart.chart_type == ChartTypeEnum.PLOT) != is_plot:
                continue
            explicit_ids.add(chart.id)
            entries[chart.id] = {
                "chart": chart,
                "order": row.order,
                "criterias": [build_explicit(c) for c in chart.tastecriteria_set.all()],
            }

        implicit_rows: dict[int, list] = {}
        for row in self._criteria_rows(obj):
            chart = row.criteria.chart
            if chart is None or (chart.chart_type == ChartTypeEnum.PLOT) != is_plot:
                continue
            if chart.id in explicit_ids:
                continue
            implicit_rows.setdefault(chart.id, []).append(row)
        for cid, rows in implicit_rows.items():
            entries[cid] = {
                "chart": rows[0].criteria.chart,
                "order": min(r.order for r in rows),
                "criterias": [build_implicit(r) for r in rows],
            }

        return [entries[cid] for cid in sorted(entries, key=lambda c: (entries[c]["order"], entries[c]["chart"].id))]

    @extend_schema_field(CHARTS_SCHEMA)
    def get_charts(self, obj: Product) -> list[dict]:
        marks = self._criteria_marks(obj)
        entries = self._collect_chart_entries(
            obj,
            is_plot=False,
            build_explicit=lambda c: self._chart_criteria_item(c, marks),
            build_implicit=lambda r: self._criteria_item(r, marks),
        )
        return [
            {
                "id": e["chart"].id,
                "name": e["chart"].name,
                "description": e["chart"].description,
                "color": e["chart"].color,
                "label_placement": e["chart"].label_placement,
                "taste_block": e["chart"].taste_block_id,
                "order": e["order"],
                "criterias": e["criterias"],
            }
            for e in entries
        ]

    @extend_schema_field(PLOTS_SCHEMA)
    def get_plots(self, obj: Product) -> list[dict]:
        points = self._plot_points(obj)
        entries = self._collect_chart_entries(
            obj,
            is_plot=True,
            build_explicit=lambda c: self._plot_series_item(c, points),
            build_implicit=lambda r: self._plot_series_item_from_row(r, points),
        )
        return [
            {
                "id": e["chart"].id,
                "name": e["chart"].name,
                "description": e["chart"].description,
                "color": e["chart"].color,
                "x_axis": e["chart"].x_axis,
                "y_axis": e["chart"].y_axis,
                "x_axis_name": e["chart"].x_axis_name,
                "y_axis_name": e["chart"].y_axis_name,
                "taste_block": e["chart"].taste_block_id,
                "order": e["order"],
                "criterias": e["criterias"],
            }
            for e in entries
        ]

    @extend_schema_field(PHRASES_SCHEMA)
    def get_phrases(self, obj: Product) -> list[dict]:
        review = self._review(obj)
        answers_by_phrase: dict[int, list] = {}
        if review:
            answers_by_phrase = {pr.phrase_template_id: pr.answers for pr in review.phrase_reviews.all()}
        out = []
        for row in obj.__dict__.get("_phrase_rows", []):
            tpl = row.phrase_template
            out.append(
                {
                    "id": tpl.id,
                    "name": tpl.name,
                    "template": tpl.template,
                    "segments": tpl.segments,
                    "blanks_count": tpl.blanks_count,
                    "taste_block": tpl.taste_block_id,
                    "order": row.order,
                    "user_answers": answers_by_phrase.get(tpl.id, []),
                }
            )
        return out

    @extend_schema_field(FREE_TEXT_PROMPTS_SCHEMA)
    def get_free_text_prompts(self, obj: Product) -> list[dict]:
        review = self._review(obj)
        text_by_prompt: dict[int, str] = {}
        if review:
            text_by_prompt = {r.free_text_prompt_id: r.text for r in review.free_text_reviews.all()}
        out = []
        for row in obj.__dict__.get("_free_text_rows", []):
            prompt = row.free_text_prompt
            out.append(
                {
                    "id": prompt.id,
                    "name": prompt.name,
                    "description": prompt.description,
                    "taste_block": prompt.taste_block_id,
                    "order": row.order,
                    "user_text": text_by_prompt.get(prompt.id, ""),
                }
            )
        return out

    # --- контекст дегустации ---

    def _photo_payload(self, photos) -> list[dict]:
        """[{id, image}] с абсолютными URL. Имя фото служебное — на фронт не отдаётся."""
        request = self.context.get("request")
        out = []
        for ph in photos:
            if not ph.image:
                continue
            url = ph.image.url
            out.append({"id": ph.id, "image": request.build_absolute_uri(url) if request else url})
        return out

    @extend_schema_field(PHOTOS_SCHEMA)
    def get_photos(self, obj: Product) -> list[dict]:
        return self._photo_payload(obj.__dict__.get("_photos", []))

    @extend_schema_field(TASTE_BLOCKS_SCHEMA)
    def get_taste_blocks(self, obj: Product) -> list[dict]:
        # Разделы карточки берём у ProductTasting (упорядочены через ProductTastingTasteBlock.order),
        # их кладёт во _taste_blocks вьюшка при сборке продуктов дегустации. Фото блока резолвим в URL здесь.
        return [
            {
                "id": tb["id"],
                "name": tb["name"],
                "show_tags": tb["show_tags"],
                "photos": self._photo_payload(tb.get("photos", [])),
            }
            for tb in obj.__dict__.get("_taste_blocks", [])
        ]

    @extend_schema_field(TEA_FLAVOR_SCHEMA)
    def get_tea_flavor_combination(self, obj: Product) -> list[dict]:
        combinations = obj.__dict__.get("_tea_flavor_combination", [])
        if not combinations:
            return []
        request = self.context.get("request")
        return [
            {
                "id": p.id,
                "name": p.name,
                "logo": _first_logo_url(p, request),
            }
            for p in combinations
        ]

    def get_category(self, obj: Product) -> str | None:
        return obj.__dict__.get("_category")

    def get_is_nominated(self, obj: Product) -> bool:
        mark = obj.__dict__.get("_current_tasting_mark")
        return bool(mark and mark.is_nominated)

    def get_podium_place(self, obj: Product) -> int | None:
        mark = obj.__dict__.get("_current_tasting_mark")
        return mark.podium_place if mark else None


def _first_logo_url(product: Product, request) -> str | None:
    if not product.image:
        return None
    url = product.image.url
    return request.build_absolute_uri(url) if request is not None else url


class TastingListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tasting
        fields = ["id", "title", "description", "type", "date"]


class TastingDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tasting
        fields = ["id", "title", "description", "result_description", "type", "date", "show_podium_candidates"]


class TastingParticipationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TastingParticipation
        fields = ["tasting", "joined_at"]
        read_only_fields = ["tasting", "joined_at"]


class TastingResultPodiumItemSerializer(serializers.Serializer):
    place = serializers.IntegerField()
    id = serializers.UUIDField()
    name = serializers.CharField()
    number = serializers.IntegerField(allow_null=True)
    total_score = serializers.IntegerField(allow_null=True)


class TastingResultFavoriteItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    number = serializers.IntegerField(allow_null=True)


class TastingResultCriteriaItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    orientation = serializers.CharField(allow_null=True)
    min_total = serializers.IntegerField()
    max_total = serializers.IntegerField()
    user_total = serializers.IntegerField()


class TastingResultChartSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    color = serializers.CharField(allow_null=True)
    label_placement = serializers.CharField()
    criterias = TastingResultCriteriaItemSerializer(many=True)


class TastingResultPlotSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    color = serializers.CharField(allow_null=True)
    x_axis = serializers.JSONField()
    y_axis = serializers.JSONField()
    x_axis_name = serializers.CharField(allow_null=True)
    y_axis_name = serializers.CharField(allow_null=True)
    criterias = TastingResultCriteriaItemSerializer(many=True)


class TastingResultTagCloudItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True, help_text="id TasteTags для source=tag; null для source=phrase.")
    name = serializers.CharField()
    weight = serializers.IntegerField(help_text="Сколько раз элемент встретился в отзывах гостя в этой дегустации.")
    source = serializers.ChoiceField(
        choices=["tag", "phrase"], help_text="`tag` — выбранный TasteTags; `phrase` — слово из пропуска PhraseTemplate."
    )


class TastingResultTeaMatchSerializer(serializers.Serializer):
    tea_id = serializers.UUIDField()
    tea_name = serializers.CharField()
    tea_logo = serializers.CharField(allow_null=True)
    product_id = serializers.UUIDField()
    product_name = serializers.CharField()
    product_number = serializers.IntegerField(allow_null=True)
    match_score = serializers.IntegerField()


ICE_CREAM_STATS_SCHEMA = {
    "type": "object",
    "additionalProperties": {
        "type": "object",
        "description": "Ключ верхнего уровня — IceCreamLogo.type (например, 'ice_cream' или 'tea').",
        "additionalProperties": {
            "type": "object",
            "description": "Ключ — IceCreamLogo.text (название позиции).",
            "properties": {
                "amount": {
                    "type": "integer",
                    "description": "Число уникальных продуктов в дегустации, у которых есть IceCreamLogo с таким type+text.",
                    "example": 2,
                },
                "image": {
                    "type": "string",
                    "format": "uri",
                    "nullable": True,
                    "description": "URL одного из IceCreamLogo.image в этой группе.",
                    "example": "https://api.example.com/media/ice_cream_logo/gelato.png",
                },
            },
            "required": ["amount", "image"],
        },
    },
    "description": (
        "Группировка IceCreamLogo всех продуктов дегустации: "
        "ice_cream_stats[<IceCreamLogo.type>][<IceCreamLogo.text>] = {amount, image}."
    ),
    "example": {
        "ice_cream": {
            "джелато": {
                "amount": 2,
                "image": "https://api.example.com/media/ice_cream_logo/gelato.png",
            },
        },
        "tea": {
            "красный чай": {
                "amount": 1,
                "image": "https://api.example.com/media/ice_cream_logo/red_tea.png",
            },
            "черный чай": {
                "amount": 1,
                "image": "https://api.example.com/media/ice_cream_logo/black_tea.png",
            },
        },
    },
}


@extend_schema_field(ICE_CREAM_STATS_SCHEMA)
class IceCreamStatsField(serializers.DictField):
    pass


class TastingResultSerializer(serializers.Serializer):
    result_id = serializers.UUIDField()
    tasting_id = serializers.UUIDField()
    title = serializers.CharField()
    type = serializers.CharField()
    result_description = serializers.CharField(allow_null=True)
    podium = TastingResultPodiumItemSerializer(many=True)
    favorites = TastingResultFavoriteItemSerializer(many=True)
    criteria_breakdown = TastingResultCriteriaItemSerializer(many=True)
    charts = TastingResultChartSerializer(many=True)
    plots = TastingResultPlotSerializer(many=True)
    tags_cloud = TastingResultTagCloudItemSerializer(many=True)
    tea_matches = TastingResultTeaMatchSerializer(many=True)
    ice_cream_stats = IceCreamStatsField()


class NominateWriteSerializer(serializers.Serializer):
    is_nominated = serializers.BooleanField(default=True)


class NominateResponseSerializer(serializers.Serializer):
    is_nominated = serializers.BooleanField()
    podium_place = serializers.IntegerField(allow_null=True)


class PodiumPatchSerializer(serializers.Serializer):
    first = serializers.UUIDField(required=False, allow_null=True)
    second = serializers.UUIDField(required=False, allow_null=True)
    third = serializers.UUIDField(required=False, allow_null=True)
    ranking = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Полный упорядоченный список product_id дегустации: место = позиция в списке "
        "(1-е = лучшее, далее 2, 3, …). Ранжирует ВСЕ переданные блюда; не вошедшие в список "
        "теряют место. Альтернатива first/second/third — нельзя слать вместе.",
    )

    def validate(self, attrs):
        if "ranking" in attrs:
            if any(k in attrs for k in ("first", "second", "third")):
                raise serializers.ValidationError("Use either `ranking` or first/second/third, not both.")
            ids = attrs["ranking"]
            if len(ids) != len(set(ids)):
                raise serializers.ValidationError({"ranking": "Duplicate product ids in ranking."})
            return attrs
        non_null = [attrs[k] for k in ("first", "second", "third") if k in attrs and attrs[k] is not None]
        if len(non_null) != len(set(non_null)):
            raise serializers.ValidationError("Same product cannot occupy multiple podium places.")
        return attrs


class PodiumSnapshotSerializer(serializers.Serializer):
    first = serializers.UUIDField(allow_null=True)
    second = serializers.UUIDField(allow_null=True)
    third = serializers.UUIDField(allow_null=True)
    ranking = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="Полный упорядоченный список product_id, у которых есть место (по возрастанию места).",
    )


class ConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = Config
        fields = ["show_share_link", "share_text"]
