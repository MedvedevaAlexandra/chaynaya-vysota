from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from .models import (
    Chart,
    ChartTypeEnum,
    Config,
    TasteTags,
    Product,
    ProductCriteriaReview,
    ProductIceCreamLogo,
    ProductPhoto,
    FreeTextPromptReview,
    PhraseTemplateReview,
    ProductReview,
    ProductTasting,
    ProductTastingChart,
    ProductTastingFreeTextPrompt,
    ProductTastingPhraseTemplate,
    ProductTastingTasteBlock,
    ProductTastingTasteCriteria,
    ProductTastingUserMark,
    TasteCriteria,
    Tasting,
    TastingParticipation,
)
from .serializers import (
    ConfigSerializer,
    NominateResponseSerializer,
    NominateWriteSerializer,
    PodiumPatchSerializer,
    PodiumSnapshotSerializer,
    ProductInTastingSerializer,
    ProductReviewWriteSerializer,
    TastingDetailSerializer,
    TastingListSerializer,
    TastingParticipationSerializer,
    TastingResultSerializer,
)


# --- сборка карточки продукта в контексте дегустации (per-ProductTasting) ---


def _pt_prefetches(user):
    """Prefetch'и для ProductTasting, чтобы собрать карточку без N+1: инфо о продукте, конфиг оценки
    (критерии/блоки этого ProductTasting), сочетания, а также отзыв и метку текущего пользователя."""
    if user.is_authenticated:
        review_qs = ProductReview.objects.filter(user=user).prefetch_related(
            "criteria_reviews", "taste_tags", "phrase_reviews", "free_text_reviews"
        )
        marks_qs = ProductTastingUserMark.objects.filter(user=user)
    else:
        review_qs = ProductReview.objects.none()
        marks_qs = ProductTastingUserMark.objects.none()
    return [
        Prefetch(
            "product",
            queryset=Product.objects.select_related("line").prefetch_related("logos", "taste_tags"),
        ),
        Prefetch("tea_flavor_combination", queryset=Product.objects.prefetch_related("logos")),
        Prefetch(
            "producttastingtastecriteria_set",
            queryset=ProductTastingTasteCriteria.objects.select_related("criteria", "criteria__chart").order_by(
                "order", "criteria__order", "criteria_id"
            ),
            to_attr="_tc_rows",
        ),
        Prefetch(
            "producttastingchart_set",
            queryset=ProductTastingChart.objects.select_related("chart")
            .prefetch_related(
                Prefetch("chart__tastecriteria_set", queryset=TasteCriteria.objects.order_by("order", "id"))
            )
            .order_by("order", "id"),
            to_attr="_chart_rows",
        ),
        Prefetch(
            "producttastingtasteblock_set",
            queryset=ProductTastingTasteBlock.objects.select_related("taste_block")
            .prefetch_related(Prefetch("photos", queryset=ProductPhoto.objects.order_by("order", "id")))
            .order_by("order", "id"),
            to_attr="_tb_rows",
        ),
        Prefetch("photos", queryset=ProductPhoto.objects.order_by("order", "id"), to_attr="_photo_rows"),
        Prefetch(
            "producttastingphrasetemplate_set",
            queryset=ProductTastingPhraseTemplate.objects.select_related("phrase_template").order_by("order", "id"),
            to_attr="_phrase_rows",
        ),
        Prefetch(
            "producttastingfreetextprompt_set",
            queryset=ProductTastingFreeTextPrompt.objects.select_related("free_text_prompt").order_by("order", "id"),
            to_attr="_free_text_rows",
        ),
        Prefetch("reviews", queryset=review_qs, to_attr="_user_reviews"),
        Prefetch("user_marks", queryset=marks_qs, to_attr="_user_marks"),
    ]


def _attach_pt_context(pt: ProductTasting) -> Product:
    """Раскладывает контекст ProductTasting в product.__dict__ под то, что читает ProductInTastingSerializer."""
    p = pt.product
    p.__dict__["_taste_criteria_rows"] = getattr(pt, "_tc_rows", [])
    p.__dict__["_taste_blocks"] = [
        {
            "id": tb.taste_block_id,
            "name": tb.taste_block.name,
            "show_tags": tb.show_tags,
            "photos": list(tb.photos.all()),
        }
        for tb in getattr(pt, "_tb_rows", [])
    ]
    p.__dict__["_photos"] = list(getattr(pt, "_photo_rows", []))
    p.__dict__["_phrase_rows"] = getattr(pt, "_phrase_rows", [])
    p.__dict__["_free_text_rows"] = getattr(pt, "_free_text_rows", [])
    p.__dict__["_chart_rows"] = getattr(pt, "_chart_rows", [])
    p.__dict__["_tea_flavor_combination"] = list(pt.tea_flavor_combination.all())
    p.__dict__["_category"] = pt.category
    user_reviews = getattr(pt, "_user_reviews", [])
    p.__dict__["_current_review"] = user_reviews[0] if user_reviews else None
    user_marks = getattr(pt, "_user_marks", [])
    p.__dict__["_current_tasting_mark"] = user_marks[0] if user_marks else None
    return p


# --- валидация присланных оценок относительно конфига конкретного ProductTasting ---


def _allowed_criteria(pt: ProductTasting) -> dict[int, TasteCriteria]:
    """Критерии, доступные для оценки в этом ProductTasting: автономные (через taste_criteria) +
    все критерии привязанных чартов (через charts). chart подгружен (нужен для валидации Plot)."""
    out: dict[int, TasteCriteria] = {}
    for c in pt.taste_criteria.select_related("chart"):
        out[c.pk] = c
    for c in TasteCriteria.objects.filter(chart__in=pt.charts.all()).select_related("chart"):
        out[c.pk] = c
    return out


def _resolve_criteria_marks(allowed: dict[int, TasteCriteria], criteria_marks: dict[str, int]) -> list[tuple]:
    try:
        wanted_ids = {int(key): mark for key, mark in criteria_marks.items()}
    except (TypeError, ValueError):
        raise ValidationError({"criteria_marks": "Keys must be integer TasteCriteria ids."})

    linked = {cid: allowed[cid] for cid in wanted_ids if cid in allowed}
    missing = sorted(wanted_ids.keys() - linked.keys())
    if missing:
        raise ValidationError(
            {"criteria_marks": f"Criteria not configured for this product in this tasting: {missing}."}
        )
    return [(linked[cid], mark) for cid, mark in wanted_ids.items()]


def _resolve_plot_marks(allowed: dict[int, TasteCriteria], plot_marks: list[dict]) -> list[tuple]:
    wanted_ids = {pm["criteria"] for pm in plot_marks}
    linked = {cid: allowed[cid] for cid in wanted_ids if cid in allowed}
    missing = sorted(wanted_ids - linked.keys())
    if missing:
        raise ValidationError({"plot_marks": f"Criteria not configured for this product in this tasting: {missing}."})

    resolved: list[tuple[TasteCriteria, int, int]] = []
    errors: list[str] = []
    for pm in plot_marks:
        criteria = linked[pm["criteria"]]
        chart = criteria.chart
        if chart is None or chart.chart_type != ChartTypeEnum.PLOT:
            errors.append(f"Criteria {criteria.pk} is not attached to a plot chart.")
            continue
        x_values = set(_axis_int_values(chart.x_axis))
        y_values = set(_axis_int_values(chart.y_axis))
        if x_values and pm["x"] not in x_values:
            errors.append(f"x={pm['x']} is off the X axis of chart {chart.pk} (criteria {criteria.pk}).")
            continue
        if y_values and pm["mark"] not in y_values:
            errors.append(f"mark={pm['mark']} is off the Y axis of chart {chart.pk} (criteria {criteria.pk}).")
            continue
        resolved.append((criteria, pm["x"], pm["mark"]))
    if errors:
        raise ValidationError({"plot_marks": errors})
    return resolved


def _resolve_taste_tags(product: Product, tag_ids: list[int]) -> list[TasteTags]:
    wanted = set(tag_ids)
    linked = list(product.taste_tags.filter(pk__in=wanted))
    missing = sorted(wanted - {t.pk for t in linked})
    if missing:
        raise ValidationError({"taste_tags": f"Tags not linked to this product: {missing}."})
    return linked


def _resolve_phrase_answers(pt: ProductTasting, phrase_answers: list[dict]) -> list[tuple]:
    wanted_ids = {pa["phrase"] for pa in phrase_answers}
    linked = {p.pk: p for p in pt.phrase_templates.filter(pk__in=wanted_ids)}
    missing = sorted(wanted_ids - linked.keys())
    if missing:
        raise ValidationError(
            {"phrase_answers": f"Phrase templates not configured for this product in this tasting: {missing}."}
        )

    resolved: list[tuple] = []
    errors: list[str] = []
    for pa in phrase_answers:
        tpl = linked[pa["phrase"]]
        answers = pa["answers"]
        if len(answers) != tpl.blanks_count:
            errors.append(f"phrase {tpl.pk}: expected {tpl.blanks_count} answers, got {len(answers)}.")
            continue
        resolved.append((tpl, answers))
    if errors:
        raise ValidationError({"phrase_answers": errors})
    return resolved


def _resolve_free_text_answers(pt: ProductTasting, free_text_answers: list[dict]) -> list[tuple]:
    wanted_ids = {fa["prompt"] for fa in free_text_answers}
    linked = {p.pk: p for p in pt.free_text_prompts.filter(pk__in=wanted_ids)}
    missing = sorted(wanted_ids - linked.keys())
    if missing:
        raise ValidationError(
            {"free_text_answers": f"Free-text prompts not configured for this product in this tasting: {missing}."}
        )
    return [(linked[fa["prompt"]], fa["text"]) for fa in free_text_answers]


class TastingViewSet(RetrieveModelMixin, GenericViewSet):

    def get_queryset(self):
        qs = Tasting.objects.all()
        if self.action in ("products", "product_detail"):
            pt_qs = ProductTasting.objects.order_by("order").prefetch_related(*_pt_prefetches(self.request.user))
            qs = qs.prefetch_related(Prefetch("producttasting_set", queryset=pt_qs, to_attr="_pt_rows"))
        return qs

    def _products_in_tasting(self, tasting: Tasting, user) -> list[Product]:
        rows = getattr(tasting, "_pt_rows", None)
        if rows is None:
            rows = list(
                ProductTasting.objects.filter(tasting=tasting).order_by("order").prefetch_related(*_pt_prefetches(user))
            )
        return [_attach_pt_context(pt) for pt in rows]

    def get_serializer_class(self):
        if self.action == "join":
            return TastingParticipationSerializer
        if self.action == "my":
            return TastingListSerializer
        return TastingDetailSerializer

    def get_permissions(self):
        if self.action in ("retrieve", "products", "product_detail"):
            return [AllowAny()]
        return [IsAuthenticated()]

    @extend_schema(responses={200: ProductInTastingSerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="products")
    def products(self, request, pk=None):
        tasting = self.get_object()
        products = self._products_in_tasting(tasting, request.user)
        return Response(ProductInTastingSerializer(products, many=True, context={"request": request}).data)

    @extend_schema(responses={200: ProductInTastingSerializer})
    @action(
        detail=True,
        methods=["get"],
        url_path=r"products/(?P<product_id>[0-9a-fA-F-]+)",
    )
    def product_detail(self, request, pk=None, product_id=None):
        tasting = self.get_object()
        products = self._products_in_tasting(tasting, request.user)
        target = next((p for p in products if str(p.id) == str(product_id)), None)
        if target is None:
            raise NotFound("Product is not part of this tasting.")
        return Response(ProductInTastingSerializer(target, context={"request": request}).data)

    @extend_schema(
        request=ProductReviewWriteSerializer,
        responses={200: ProductInTastingSerializer, 201: ProductInTastingSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path=r"products/(?P<product_id>[0-9a-fA-F-]+)/review",
        permission_classes=[IsAuthenticated],
    )
    def review(self, request, pk=None, product_id=None):
        tasting = self.get_object()
        pt = ProductTasting.objects.filter(tasting=tasting, product_id=product_id).first()
        if pt is None:
            raise NotFound("Product is not part of this tasting.")

        payload = ProductReviewWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        criteria_marks = data.get("criteria_marks")
        plot_marks = data.get("plot_marks")
        allowed = _allowed_criteria(pt) if (criteria_marks or plot_marks) else {}
        criteria_pairs = _resolve_criteria_marks(allowed, criteria_marks) if criteria_marks else []
        plot_triples = _resolve_plot_marks(allowed, plot_marks) if plot_marks else []

        phrase_answers = data.get("phrase_answers")
        phrase_pairs = _resolve_phrase_answers(pt, phrase_answers) if phrase_answers else []

        free_text_answers = data.get("free_text_answers")
        free_text_pairs = _resolve_free_text_answers(pt, free_text_answers) if free_text_answers else []

        tag_ids = data.get("taste_tags")
        resolved_tags = _resolve_taste_tags(pt.product, tag_ids) if tag_ids is not None else None

        meaningful_keys = {
            "global_comment",
            "self_comment",
            "composition",
            "criteria_marks",
            "plot_marks",
            "phrase_answers",
            "free_text_answers",
            "taste_tags",
        }
        implies_tasted = bool(meaningful_keys & data.keys())

        with transaction.atomic():
            review, created = ProductReview.objects.get_or_create(user=request.user, product_tasting=pt)

            for field in ("global_comment", "self_comment", "composition", "tasted", "is_bookmarked"):
                if field in data:
                    setattr(review, field, data[field])
            if implies_tasted and not review.tasted:
                review.tasted = True
            review.save()

            for criteria, mark in criteria_pairs:
                ProductCriteriaReview.objects.update_or_create(
                    product_review=review,
                    criteria=criteria,
                    x=None,
                    defaults={"mark": mark},
                )

            for criteria, x, mark in plot_triples:
                ProductCriteriaReview.objects.update_or_create(
                    product_review=review,
                    criteria=criteria,
                    x=x,
                    defaults={"mark": mark},
                )

            for tpl, answers in phrase_pairs:
                PhraseTemplateReview.objects.update_or_create(
                    product_review=review,
                    phrase_template=tpl,
                    defaults={"answers": answers},
                )

            for prompt, text in free_text_pairs:
                FreeTextPromptReview.objects.update_or_create(
                    product_review=review,
                    free_text_prompt=prompt,
                    defaults={"text": text},
                )

            if resolved_tags is not None:
                review.taste_tags.set(resolved_tags)

        pt_full = ProductTasting.objects.filter(pk=pt.pk).prefetch_related(*_pt_prefetches(request.user)).first()
        product = _attach_pt_context(pt_full)
        return Response(
            ProductInTastingSerializer(product, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(request=None, responses={200: TastingParticipationSerializer, 201: TastingParticipationSerializer})
    @action(detail=True, methods=["post"], url_path="join")
    def join(self, request, pk=None):
        tasting = self.get_object()
        with transaction.atomic():
            participation, created = TastingParticipation.objects.get_or_create(
                tasting=tasting,
                user=request.user,
            )
            # Отзыв теперь привязан к ProductTasting; заводим «голую» запись с tasted=True на каждую позицию.
            pt_pairs = list(ProductTasting.objects.filter(tasting=tasting).values_list("id", "product_id"))
            ProductReview.objects.bulk_create(
                [
                    ProductReview(user=request.user, product_tasting_id=ptid, product_id=pid, tasted=True)
                    for ptid, pid in pt_pairs
                ],
                ignore_conflicts=True,
            )
            ProductReview.objects.filter(
                user=request.user,
                product_tasting__tasting=tasting,
                tasted=False,
            ).update(tasted=True)
        serializer = self.get_serializer(participation)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(responses={200: TastingListSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="my")
    def my(self, request):
        qs = Tasting.objects.filter(participants=request.user).order_by("-date")
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(request=None, responses={200: ProductInTastingSerializer})
    @action(
        detail=True,
        methods=["delete"],
        url_path=r"products/(?P<product_id>[0-9a-fA-F-]+)/charts/(?P<chart_id>[0-9]+)/marks",
        permission_classes=[IsAuthenticated],
    )
    def clear_chart_marks(self, request, pk=None, product_id=None, chart_id=None):
        """Очистить оценки гостя по конкретному plot-чарту этой позиции («очистить график»).
        Удаляет все ProductCriteriaReview по критериям этого чарта в отзыве текущего юзера."""
        tasting = self.get_object()
        pt = ProductTasting.objects.filter(tasting=tasting, product_id=product_id).first()
        if pt is None:
            raise NotFound("Product is not part of this tasting.")

        chart = Chart.objects.filter(pk=chart_id, chart_type=ChartTypeEnum.PLOT).first()
        if chart is None:
            raise NotFound("Plot chart not found.")

        # Чарт должен быть сконфигурирован для этой позиции (явно через charts или через входящие критерии).
        allowed = _allowed_criteria(pt)
        chart_criteria_ids = [cid for cid, c in allowed.items() if c.chart_id == chart.pk]
        if not chart_criteria_ids:
            raise NotFound("Chart is not configured for this product in this tasting.")

        review = ProductReview.objects.filter(user=request.user, product_tasting=pt).first()
        if review is not None:
            ProductCriteriaReview.objects.filter(
                product_review=review, criteria_id__in=chart_criteria_ids
            ).delete()

        pt_full = ProductTasting.objects.filter(pk=pt.pk).prefetch_related(*_pt_prefetches(request.user)).first()
        product = _attach_pt_context(pt_full)
        return Response(ProductInTastingSerializer(product, context={"request": request}).data)

    @extend_schema(request=NominateWriteSerializer, responses={200: NominateResponseSerializer})
    @action(
        detail=True,
        methods=["post"],
        url_path=r"products/(?P<product_id>[0-9a-fA-F-]+)/nominate",
        permission_classes=[IsAuthenticated],
    )
    def nominate(self, request, pk=None, product_id=None):
        tasting = self.get_object()
        product_tasting = ProductTasting.objects.filter(tasting=tasting, product_id=product_id).first()
        if product_tasting is None:
            raise NotFound("Product is not part of this tasting.")

        body = NominateWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        is_nominated = body.validated_data["is_nominated"]

        mark, created = ProductTastingUserMark.objects.get_or_create(
            user=request.user,
            product_tasting=product_tasting,
            defaults={"is_nominated": is_nominated},
        )
        if not created and mark.is_nominated != is_nominated:
            mark.is_nominated = is_nominated
            mark.save(update_fields=["is_nominated", "updated_at"])

        return Response({"is_nominated": mark.is_nominated, "podium_place": mark.podium_place})

    @extend_schema(request=PodiumPatchSerializer, responses={200: PodiumSnapshotSerializer})
    @action(detail=True, methods=["patch"], url_path="podium", permission_classes=[IsAuthenticated])
    def podium(self, request, pk=None):
        tasting = self.get_object()
        body = PodiumPatchSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        place_to_field = {1: "first", 2: "second", 3: "third"}

        with transaction.atomic():
            if "ranking" in data:
                self._set_full_ranking(request.user, tasting, data["ranking"])
            else:
                self._set_top3(request.user, tasting, data)

        snapshot = {"first": None, "second": None, "third": None, "ranking": []}
        current = (
            ProductTastingUserMark.objects.filter(
                user=request.user,
                tasting=tasting,
                podium_place__isnull=False,
            )
            .select_related("product_tasting")
            .order_by("podium_place")
        )
        for m in current:
            if m.podium_place in place_to_field:
                snapshot[place_to_field[m.podium_place]] = m.product_tasting.product_id
            snapshot["ranking"].append(m.product_tasting.product_id)
        return Response(snapshot)

    @staticmethod
    def _set_top3(user, tasting, data):
        """Режим топ-3: точечно ставит/снимает места 1..3 по ключам first/second/third."""
        field_to_place = {"first": 1, "second": 2, "third": 3}
        for field, place in field_to_place.items():
            if field not in data:
                continue
            target_product_id = data[field]
            ProductTastingUserMark.objects.filter(user=user, tasting=tasting, podium_place=place).update(
                podium_place=None
            )
            if target_product_id is None:
                continue
            pt = ProductTasting.objects.filter(tasting=tasting, product_id=target_product_id).first()
            if pt is None:
                raise NotFound(f"Product {target_product_id} is not part of this tasting.")
            mark, _ = ProductTastingUserMark.objects.get_or_create(user=user, product_tasting=pt)
            mark.podium_place = place
            mark.save(update_fields=["podium_place", "updated_at"])

    @staticmethod
    def _set_full_ranking(user, tasting, product_ids):
        """Полный рейтинг: место = позиция в списке (1..N). Все прежние места очищаются,
        переданные блюда ранжируются по порядку; не вошедшие остаются без места."""
        pts = {pt.product_id: pt for pt in ProductTasting.objects.filter(tasting=tasting, product_id__in=product_ids)}
        missing = [str(pid) for pid in product_ids if pid not in pts]
        if missing:
            raise NotFound(f"Products not part of this tasting: {missing}.")
        ProductTastingUserMark.objects.filter(user=user, tasting=tasting, podium_place__isnull=False).update(
            podium_place=None
        )
        for place, pid in enumerate(product_ids, start=1):
            mark, _ = ProductTastingUserMark.objects.get_or_create(user=user, product_tasting=pts[pid])
            mark.podium_place = place
            mark.save(update_fields=["podium_place", "updated_at"])

    @extend_schema(responses={200: TastingResultSerializer})
    @action(detail=True, methods=["get"], url_path="result", permission_classes=[IsAuthenticated])
    def result(self, request, pk=None):
        tasting = self.get_object()
        participation = TastingParticipation.objects.filter(
            tasting=tasting,
            user=request.user,
        ).first()
        if participation is None:
            raise NotFound("You have not joined this tasting.")
        return Response(_build_tasting_result(participation, request))


class ResultViewSet(RetrieveModelMixin, GenericViewSet):
    queryset = TastingParticipation.objects.select_related("tasting", "user")
    permission_classes = [AllowAny]
    serializer_class = TastingResultSerializer

    @extend_schema(responses={200: TastingResultSerializer})
    def retrieve(self, request, *args, **kwargs):
        participation = self.get_object()
        return Response(_build_tasting_result(participation, request))


class ConfigView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: ConfigSerializer})
    def get(self, request):
        return Response(ConfigSerializer(Config.load()).data)


def _build_tasting_result(participation: TastingParticipation, request) -> dict:
    tasting = participation.tasting
    user = participation.user

    # В результат как «подиум» идут только места 1..3, даже если гость отранжировал все блюда.
    podium_marks = list(
        ProductTastingUserMark.objects.filter(
            user=user,
            tasting=tasting,
            podium_place__lte=3,
        )
        .select_related("product_tasting__product")
        .order_by("podium_place")
    )
    favorite_marks = list(
        ProductTastingUserMark.objects.filter(
            user=user,
            tasting=tasting,
            is_nominated=True,
            podium_place__isnull=True,
        ).select_related("product_tasting__product")
    )

    podium_pt_ids = [m.product_tasting_id for m in podium_marks]
    reviews_by_pt = {
        r.product_tasting_id: r
        for r in ProductReview.objects.filter(user=user, product_tasting_id__in=podium_pt_ids).prefetch_related(
            "criteria_reviews", "taste_tags"
        )
    }

    podium = [
        {
            "place": m.podium_place,
            "id": m.product_tasting.product_id,
            "name": m.product_tasting.product.name,
            "number": m.product_tasting.product.number,
            "total_score": _review_total_score(reviews_by_pt.get(m.product_tasting_id)),
        }
        for m in podium_marks
    ]
    favorites = [
        {
            "id": m.product_tasting.product_id,
            "name": m.product_tasting.product.name,
            "number": m.product_tasting.product.number,
        }
        for m in favorite_marks
    ]

    # Конфиг оценки берём с уровня ProductTasting этой дегустации из ТРЁХ источников:
    # 1) автономные критерии (chart IS NULL) через taste_criteria;
    # 2) критерии ЯВНО привязанных чартов (charts) — весь чарт;
    # 3) критерии чартов, добавленные через taste_criteria поштучно, чей чарт НЕ привязан явно к этой
    #    позиции — подмножество (обратная совместимость).
    # criteria_product_count — сколько позиций дегустации содержат критерий (на каждую позицию по +1);
    # пару (позиция, критерий) учитываем один раз, даже если она есть и в charts, и в through.
    criteria_obj_by_id: dict[int, TasteCriteria] = {}
    criteria_product_count: dict[int, int] = defaultdict(int)
    counted_pairs: set[tuple] = set()  # (product_tasting_id, criteria_id)

    standalone_rows = ProductTastingTasteCriteria.objects.filter(
        product_tasting__tasting=tasting, criteria__chart__isnull=True
    ).select_related("criteria")
    for row in standalone_rows:
        criteria_obj_by_id[row.criteria_id] = row.criteria
        if (row.product_tasting_id, row.criteria_id) not in counted_pairs:
            counted_pairs.add((row.product_tasting_id, row.criteria_id))
            criteria_product_count[row.criteria_id] += 1

    chart_rows = (
        ProductTastingChart.objects.filter(product_tasting__tasting=tasting)
        .select_related("chart")
        .prefetch_related(Prefetch("chart__tastecriteria_set", queryset=TasteCriteria.objects.select_related("chart")))
    )
    for row in chart_rows:
        for criteria in row.chart.tastecriteria_set.all():
            criteria_obj_by_id[criteria.id] = criteria
            if (row.product_tasting_id, criteria.id) not in counted_pairs:
                counted_pairs.add((row.product_tasting_id, criteria.id))
                criteria_product_count[criteria.id] += 1

    implicit_chart_rows = ProductTastingTasteCriteria.objects.filter(
        product_tasting__tasting=tasting, criteria__chart__isnull=False
    ).select_related("criteria", "criteria__chart")
    for row in implicit_chart_rows:
        criteria_obj_by_id[row.criteria_id] = row.criteria
        if (row.product_tasting_id, row.criteria_id) not in counted_pairs:
            counted_pairs.add((row.product_tasting_id, row.criteria_id))
            criteria_product_count[row.criteria_id] += 1

    user_totals: dict[int, int] = defaultdict(int)
    if criteria_obj_by_id:
        user_mark_rows = ProductCriteriaReview.objects.filter(
            product_review__user=user,
            product_review__product_tasting__tasting=tasting,
            criteria_id__in=criteria_obj_by_id.keys(),
        ).values_list("criteria_id", "mark")
        for cid, mark in user_mark_rows:
            user_totals[cid] += mark

    criteria_breakdown: list[dict] = []
    charts_by_id: dict[int, dict] = {}
    chart_objects: dict = {}
    plots_by_id: dict[int, dict] = {}
    plot_objects: dict = {}
    for criteria in sorted(criteria_obj_by_id.values(), key=lambda c: (c.order, c.id)):
        cid = criteria.id
        count = criteria_product_count[cid]
        chart = criteria.chart
        is_plot = chart is not None and chart.chart_type == ChartTypeEnum.PLOT

        if is_plot:
            # Y-шкала и деления X заданы на самом чарте; всего ячеек = продукты × деления X.
            values = _axis_int_values(chart.y_axis)
            num_x = len(_axis_int_values(chart.x_axis)) or 1
            cells = count * num_x
        else:
            values = _axis_int_values(criteria.grade or [])
            cells = count

        min_total = (min(values) * cells) if values else 0
        max_total = (max(values) * cells) if values else 0
        item_dict = {
            "id": cid,
            "name": criteria.name,
            "description": criteria.description,
            "orientation": criteria.orientation,
            "min_total": min_total,
            "max_total": max_total,
            "user_total": user_totals.get(cid, 0),
        }
        if chart is None:
            criteria_breakdown.append(item_dict)
        elif is_plot:
            bucket = plots_by_id.get(chart.id)
            if bucket is None:
                bucket = {
                    "id": chart.id,
                    "name": chart.name,
                    "description": chart.description,
                    "color": chart.color,
                    "x_axis": chart.x_axis,
                    "y_axis": chart.y_axis,
                    "x_axis_name": chart.x_axis_name,
                    "y_axis_name": chart.y_axis_name,
                    "criterias": [],
                }
                plots_by_id[chart.id] = bucket
                plot_objects[chart.id] = chart
            bucket["criterias"].append(item_dict)
        else:
            bucket = charts_by_id.get(chart.id)
            if bucket is None:
                bucket = {
                    "id": chart.id,
                    "name": chart.name,
                    "description": chart.description,
                    "color": chart.color,
                    "label_placement": chart.label_placement,
                    "criterias": [],
                }
                charts_by_id[chart.id] = bucket
                chart_objects[chart.id] = chart
            bucket["criterias"].append(item_dict)

    charts_breakdown = [
        charts_by_id[cid] for cid in sorted(charts_by_id, key=lambda c: (chart_objects[c].order, chart_objects[c].id))
    ]
    plots_breakdown = [
        plots_by_id[cid] for cid in sorted(plots_by_id, key=lambda c: (plot_objects[c].order, plot_objects[c].id))
    ]

    # Облако тегов: ВСЕ выбранные теги + слова из заполненных пропусков PhraseTemplate.
    # weight = сколько раз элемент встретился в отзывах гостя в этой дегустации.
    tag_rows = TasteTags.objects.filter(
        reviews__user=user,
        reviews__product_tasting__tasting=tasting,
    ).annotate(count=Count("reviews", distinct=True))
    # Только выбранные TasteTags. Поле `source` оставляем в схеме для обратной совместимости
    # (заполнения фраз-шаблонов в облако больше не попадают).
    tags_cloud = [{"id": t.id, "name": t.name, "weight": t.count, "source": "tag"} for t in tag_rows]
    tags_cloud.sort(key=lambda x: (-x["weight"], x["name"]))

    pt_with_combos = (
        ProductTasting.objects.filter(tasting=tasting)
        .select_related("product")
        .prefetch_related(
            Prefetch("tea_flavor_combination", queryset=Product.objects.prefetch_related("logos")),
        )
    )
    tea_obj_by_id: dict = {}
    tea_to_products: dict = defaultdict(set)
    product_obj_by_id: dict = {}
    for pt in pt_with_combos:
        product_obj_by_id[pt.product_id] = pt.product
        for tea in pt.tea_flavor_combination.all():
            tea_obj_by_id[tea.id] = tea
            tea_to_products[tea.id].add(pt.product_id)

    match_criteria_ids = set(
        ProductTastingTasteCriteria.objects.filter(
            product_tasting__tasting=tasting,
            for_tea_combination=True,
        )
        .values_list("criteria_id", flat=True)
        .distinct()
    )
    match_scores: dict = defaultdict(int)
    if match_criteria_ids and tea_to_products:
        match_rows = ProductCriteriaReview.objects.filter(
            product_review__user=user,
            product_review__product_tasting__tasting=tasting,
            criteria_id__in=match_criteria_ids,
        ).values_list("product_review__product_id", "mark")
        for pid, mark in match_rows:
            match_scores[pid] += mark

    tea_matches = []
    for tea_id, paired_pids in tea_to_products.items():
        scored = [(pid, match_scores[pid]) for pid in paired_pids if pid in match_scores]
        if not scored:
            continue
        scored.sort(key=lambda x: (-x[1], str(x[0])))
        top_pid, top_score = scored[0]
        tea = tea_obj_by_id[tea_id]
        top_product = product_obj_by_id[top_pid]
        tea_matches.append(
            {
                "tea_id": tea.id,
                "tea_name": tea.name,
                "tea_logo": _file_url(tea.image, request),
                "product_id": top_product.id,
                "product_name": top_product.name,
                "product_number": top_product.number,
                "match_score": top_score,
            }
        )
    tea_matches.sort(key=lambda x: (x["tea_name"] or "", str(x["tea_id"])))

    ice_cream_stats = _ice_cream_stats(_reviewed_product_ids(user, tasting), request)

    return {
        "result_id": participation.id,
        "tasting_id": tasting.id,
        "title": tasting.title,
        "type": tasting.type,
        "result_description": tasting.result_description,
        "podium": podium,
        "favorites": favorites,
        "criteria_breakdown": criteria_breakdown,
        "charts": charts_breakdown,
        "plots": plots_breakdown,
        "tags_cloud": tags_cloud,
        "tea_matches": tea_matches,
        "ice_cream_stats": ice_cream_stats,
    }


def _review_total_score(review: ProductReview | None) -> int | None:
    if review is None:
        return None
    marks_sum = sum(cr.mark for cr in review.criteria_reviews.all())
    weights_sum = sum(t.weight for t in review.taste_tags.all())
    total = Decimal(str(marks_sum + weights_sum))
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _reviewed_product_ids(user, tasting: Tasting) -> set:
    reviews = ProductReview.objects.filter(user=user, product_tasting__tasting=tasting).prefetch_related(
        "criteria_reviews", "taste_tags"
    )
    reviewed: set = set()
    for r in reviews:
        if (
            r.global_comment
            or r.self_comment
            or r.composition
            or list(r.criteria_reviews.all())
            or list(r.taste_tags.all())
        ):
            reviewed.add(r.product_id)
    return reviewed


def _ice_cream_stats(product_ids, request) -> dict[str, dict[str, dict]]:
    if not product_ids:
        return {}
    rows = ProductIceCreamLogo.objects.filter(product_id__in=product_ids).select_related("logo").order_by("id")

    products_by_bucket: dict[tuple[str, str], set] = defaultdict(set)
    image_by_bucket: dict[tuple[str, str], str | None] = {}
    for row in rows:
        logo = row.logo
        text = logo.text
        if not text:
            continue
        key = (logo.type, text)
        products_by_bucket[key].add(row.product_id)
        if key not in image_by_bucket:
            image_by_bucket[key] = _file_url(logo.image, request)

    stats: dict[str, dict[str, dict]] = defaultdict(dict)
    for (type_, text), pids in products_by_bucket.items():
        stats[type_][text] = {
            "amount": len(pids),
            "image": image_by_bucket.get((type_, text)),
        }
    return stats


def _axis_int_values(items) -> list[int]:
    """Достаёт целые value из grade-подобного списка [{value, label}, ...], пропуская мусор."""
    values: list[int] = []
    for item in items or []:
        try:
            values.append(int(item["value"]))
        except (KeyError, TypeError, ValueError):
            continue
    return values


def _file_url(file_field, request) -> str | None:
    if not file_field:
        return None
    url = file_field.url
    return request.build_absolute_uri(url) if request is not None else url
