
import json
import math
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import numpy as np
import psycopg2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

DB_URL = "postgresql://benomen:AAVolodko6872!@138.16.178.46:5432/vysota"
TASTING_ID = "32d7f152-2880-4ed6-af9d-a52036b934fb"
OUT_DIR = Path("/workspace/infographics_last_tasting_simple")
OUT_DIR.mkdir(exist_ok=True)

START_UTC = "2026-05-31 16:00:00+00"  # 19:00 MSK
END_UTC = "2026-06-01 12:00:00+00"    # morning / before noon UTC window

PRODUCT_SHORT_NAMES = {
    0: "Люйча\nformosensis",
    1: "Бай\nМэйжэнь",
    2: "Хунча\nformosensis",
    3: "Тайвань\nЧэн Ча",
    4: "Тяньчи\nУлун",
}

PRODUCT_LONG_NAMES = {
    0: "Гаосюн Ефан Чаюань Люйча var. formosensis",
    1: "Люгуй Чацюй Бай Мэйжэнь",
    2: "Люгуй Чацюй Ефан Чаюань Хунча var. formosensis",
    3: "Гаосюн Ефан Чаюань Тайвань Чэн Ча",
    4: "Дагуаньтин Тяньчи Тансян Цинсинь Улун",
}

COLORS = ["#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#B07AA1", "#76B7B2", "#EDC948", "#9C755F", "#BAB0AC"]


def slugify(text: str) -> str:
    text = text.lower()
    repl = {
        "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
    }
    text = "".join(repl.get(ch, ch) for ch in text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:70]


def as_float(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def median(values):
    if not values:
        return None
    arr = sorted(values)
    n = len(arr)
    mid = n // 2
    if n % 2:
        return arr[mid]
    return (arr[mid - 1] + arr[mid]) / 2


def format_num(value):
    if value is None:
        return "—"
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def get_data():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # SELECT-only query: participants in the requested window.
    cur.execute(
        """
        SELECT tp.user_id, COALESCE(NULLIF(u.first_name, ''), u.username) AS name,
               tp.joined_at AT TIME ZONE 'Europe/Moscow' AS joined_msk
        FROM catalog_tastingparticipation tp
        JOIN users_user u ON u.id = tp.user_id
        WHERE tp.tasting_id = %s
          AND tp.joined_at >= TIMESTAMPTZ %s
          AND tp.joined_at <  TIMESTAMPTZ %s
        ORDER BY tp.joined_at
        """,
        (TASTING_ID, START_UTC, END_UTC),
    )
    participants = cur.fetchall()
    participant_ids = [row[0] for row in participants]

    # SELECT-only query: all teas in the tasting.
    cur.execute(
        """
        SELECT pt.id, pt."order", p.name
        FROM catalog_producttasting pt
        JOIN catalog_product p ON p.id = pt.product_id
        WHERE pt.tasting_id = %s
        ORDER BY pt."order", pt.id
        """,
        (TASTING_ID,),
    )
    teas = cur.fetchall()

    # SELECT-only query: all numeric criterion marks for selected participants.
    cur.execute(
        """
        SELECT tc.id AS criteria_id,
               tc.name AS criteria_name,
               tc.grade AS grade_json,
               COALESCE(tb.name, 'РАЗДЕЛ ОЦЕНКИ: органолептика заваренного чая') AS block_name,
               pt."order" AS tea_order,
               pcr.mark AS mark,
               pr.user_id AS user_id
        FROM catalog_productcriteriareview pcr
        JOIN catalog_productreview pr ON pr.id = pcr.product_review_id
        JOIN catalog_producttasting pt ON pt.id = pr.product_tasting_id
        JOIN catalog_tastecriteria tc ON tc.id = pcr.criteria_id
        LEFT JOIN catalog_tasteblock tb ON tb.id = tc.taste_block_id
        WHERE pt.tasting_id = %s
          AND pr.user_id IN (
            SELECT tp.user_id
            FROM catalog_tastingparticipation tp
            WHERE tp.tasting_id = %s
              AND tp.joined_at >= TIMESTAMPTZ %s
              AND tp.joined_at <  TIMESTAMPTZ %s
          )
        ORDER BY tc.id, pt."order", pcr.mark
        """,
        (TASTING_ID, TASTING_ID, START_UTC, END_UTC),
    )
    marks = cur.fetchall()

    # SELECT-only query: selected catalog tags on product reviews.
    cur.execute(
        """
        SELECT tt.name AS tag_name, pt."order" AS tea_order, COUNT(*) AS cnt
        FROM catalog_productreview_taste_tags prtt
        JOIN catalog_tastetags tt ON tt.id = prtt.tastetags_id
        JOIN catalog_productreview pr ON pr.id = prtt.productreview_id
        JOIN catalog_producttasting pt ON pt.id = pr.product_tasting_id
        WHERE pt.tasting_id = %s
          AND pr.user_id IN (
            SELECT tp.user_id
            FROM catalog_tastingparticipation tp
            WHERE tp.tasting_id = %s
              AND tp.joined_at >= TIMESTAMPTZ %s
              AND tp.joined_at <  TIMESTAMPTZ %s
          )
        GROUP BY tt.name, pt."order"
        ORDER BY COUNT(*) DESC, tt.name
        """,
        (TASTING_ID, TASTING_ID, START_UTC, END_UTC),
    )
    tags = cur.fetchall()

    # SELECT-only query: free-text comments.
    cur.execute(
        """
        SELECT pt."order" AS tea_order, fp.name AS prompt_name, fpr.text
        FROM catalog_freetextpromptreview fpr
        JOIN catalog_productreview pr ON pr.id = fpr.product_review_id
        JOIN catalog_producttasting pt ON pt.id = pr.product_tasting_id
        JOIN catalog_freetextprompt fp ON fp.id = fpr.free_text_prompt_id
        WHERE pt.tasting_id = %s
          AND pr.user_id IN (
            SELECT tp.user_id
            FROM catalog_tastingparticipation tp
            WHERE tp.tasting_id = %s
              AND tp.joined_at >= TIMESTAMPTZ %s
              AND tp.joined_at <  TIMESTAMPTZ %s
          )
          AND NULLIF(TRIM(fpr.text), '') IS NOT NULL
        ORDER BY pt."order", fp.id
        """,
        (TASTING_ID, TASTING_ID, START_UTC, END_UTC),
    )
    free_texts = cur.fetchall()

    cur.close()
    conn.close()
    return participants, teas, marks, tags, free_texts


def build_criteria(marks):
    criteria = {}
    per_criterion = defaultdict(lambda: defaultdict(list))
    for cid, cname, grade_json, block_name, tea_order, mark, user_id in marks:
        criteria[cid] = {
            "id": cid,
            "name": cname,
            "grade": grade_json or [],
            "block": block_name,
        }
        per_criterion[cid][tea_order].append(mark)
    return criteria, per_criterion


def draw_criterion_chart(criterion, tea_marks, participants_count):
    cid = criterion["id"]
    cname = criterion["name"]
    block = criterion["block"].replace("РАЗДЕЛ ОЦЕНКИ: ", "")
    grade = criterion["grade"] or []

    all_marks = sorted({m for marks in tea_marks.values() for m in marks})
    if grade:
        grade_values = [int(g["value"]) for g in grade]
        x_values = sorted(set(grade_values) | set(all_marks))
        grade_label_by_value = {int(g["value"]): g["label"] for g in grade}
    else:
        if all_marks:
            lo = min(0, min(all_marks))
            hi = max(10, max(all_marks))
            x_values = list(range(lo, hi + 1))
        else:
            x_values = list(range(0, 11))
        grade_label_by_value = {}

    fig = plt.figure(figsize=(13, 8), facecolor="white")
    gs = fig.add_gridspec(2, 1, height_ratios=[1.05, 1.25], hspace=0.35)

    fig.suptitle(cname, fontsize=18, fontweight="bold", y=0.985)
    fig.text(0.5, 0.94, f"Последняя дегустация: 31 мая после 19:00 и утро 1 июня · участников: {participants_count} · все 5 чаёв",
             ha="center", fontsize=10, color="#444")
    fig.text(0.5, 0.915, f"Раздел: {block}", ha="center", fontsize=10, color="#666")

    # Top: mean/range by tea.
    ax = fig.add_subplot(gs[0])
    ax.set_title("Среднее значение и разброс оценок по каждому чаю", fontsize=12, pad=10)
    y_positions = np.arange(5)[::-1]
    ax.set_yticks(y_positions)
    ax.set_yticklabels([f"Чай {i + 1}: {PRODUCT_SHORT_NAMES[i].replace(chr(10), ' ')}" for i in range(5)], fontsize=10)

    xmin = min(x_values) - 0.5
    xmax = max(x_values) + 0.5
    ax.set_xlim(xmin, xmax)
    ax.set_xticks(x_values)
    ax.grid(axis="x", color="#dddddd", linewidth=0.8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)

    for tea_order in range(5):
        y = y_positions[tea_order]
        values = sorted(tea_marks.get(tea_order, []))
        if not values:
            ax.text(xmin + 0.05, y, "нет оценок", va="center", ha="left", color="#888", fontsize=10)
            continue
        avg = float(np.mean(values))
        med = median(values)
        mn = min(values)
        mx = max(values)
        if mn != mx:
            ax.plot([mn, mx], [y, y], color="#999999", linewidth=6, alpha=0.35, solid_capstyle="round")
        ax.scatter(values, [y] * len(values), color="#bbbbbb", s=55, alpha=0.65, zorder=2, label=None)
        ax.scatter([avg], [y], color="#1f77b4", s=125, zorder=3)
        ax.text(xmax + 0.05, y, f"n={len(values)} · ср={format_num(avg)} · мед={format_num(med)} · min={mn} · max={mx}",
                va="center", fontsize=10, color="#222", clip_on=False)

    if grade_label_by_value:
        for value, label in grade_label_by_value.items():
            ax.text(value, -0.65, f"{value}\n{label}", ha="center", va="top", fontsize=8, color="#555")
        ax.set_ylim(-1.15, 4.6)
    else:
        ax.set_xlabel("Оценка", fontsize=10)
        ax.set_ylim(-0.7, 4.6)

    # Bottom: distribution table as heatmap.
    ax2 = fig.add_subplot(gs[1])
    ax2.set_title("Распределение: сколько участников поставили каждую оценку", fontsize=12, pad=10)
    matrix = []
    for tea_order in range(5):
        c = Counter(tea_marks.get(tea_order, []))
        matrix.append([c.get(x, 0) for x in x_values])
    arr = np.array(matrix)
    vmax = max(1, int(arr.max()) if arr.size else 1)
    im = ax2.imshow(arr, cmap="Blues", aspect="auto", vmin=0, vmax=vmax)

    ax2.set_yticks(range(5))
    ax2.set_yticklabels([f"Чай {i + 1}" for i in range(5)], fontsize=10)
    ax2.set_xticks(range(len(x_values)))
    ax2.set_xticklabels([str(x) for x in x_values], fontsize=10)
    ax2.set_xlabel("Оценка", fontsize=10)

    for i in range(5):
        for j, x in enumerate(x_values):
            val = int(arr[i, j])
            text_color = "white" if val > vmax / 2 else "#222"
            ax2.text(j, i, str(val) if val else "", ha="center", va="center", fontsize=11, color=text_color, fontweight="bold")

    # Add right side with exact list of scores.
    for i in range(5):
        values = sorted(tea_marks.get(i, []))
        label = ", ".join(map(str, values)) if values else "—"
        ax2.text(len(x_values) + 0.25, i, f"{PRODUCT_SHORT_NAMES[i].replace(chr(10), ' ')}: {label}",
                 va="center", fontsize=9, color="#333", clip_on=False)

    ax2.text(len(x_values) + 0.25, -0.75, "Сырые оценки", fontsize=9, color="#333", fontweight="bold", clip_on=False)
    ax2.set_xlim(-0.5, len(x_values) + 4.5)

    # Footnote.
    fig.text(0.5, 0.025, "Источник: только SELECT-запросы к БД; данные не изменялись. Оценки учитывают только участников выбранного окна.",
             ha="center", fontsize=9, color="#777")

    filename = OUT_DIR / f"{cid:02d}_{slugify(cname)}.jpg"
    fig.savefig(filename, format="jpeg", dpi=150, bbox_inches="tight", pil_kwargs={"quality": 95})
    plt.close(fig)
    return filename


def draw_summary(participants, teas, criteria, per_criterion, tags, free_texts):
    fig = plt.figure(figsize=(12, 9), facecolor="white")
    fig.suptitle("Последняя дегустация · сводка данных", fontsize=18, fontweight="bold", y=0.98)
    fig.text(0.5, 0.94, "31 мая после 19:00 МСК и утро 1 июня · только SELECT-запросы", ha="center", fontsize=11, color="#444")

    lines = []
    lines.append(f"Участников в выбранном окне: {len(participants)}")
    lines.append(f"Чаёв в дегустации: {len(teas)}")
    lines.append(f"Критериев с оценками: {len(criteria)}")
    lines.append("")
    lines.append("Чаи:")
    for pt_id, order, name in teas:
        lines.append(f"  {order + 1}. {name}")
    lines.append("")
    lines.append("Критерии и покрытие:")
    for cid in sorted(criteria):
        total_marks = sum(len(per_criterion[cid].get(t, [])) for t in range(5))
        teas_with = sum(1 for t in range(5) if per_criterion[cid].get(t))
        lines.append(f"  {cid}. {criteria[cid]['name']} — {total_marks} оценок, чаи с оценками: {teas_with}/5")
    lines.append("")
    lines.append("Топ выбранных тэгов:")
    total_tags = Counter()
    for tag_name, tea_order, cnt in tags:
        total_tags[tag_name] += cnt
    if total_tags:
        for tag, cnt in total_tags.most_common(12):
            lines.append(f"  {tag}: {cnt}")
    else:
        lines.append("  нет выбранных тэгов")
    lines.append("")
    lines.append("Свободные текстовые комментарии:")
    if free_texts:
        for tea_order, prompt, text in free_texts[:8]:
            short = text.replace("\n", " ")[:110]
            suffix = "..." if len(text) > 110 else ""
            lines.append(f"  Чай {tea_order + 1}: {short}{suffix}")
    else:
        lines.append("  нет текстовых комментариев")

    ax = fig.add_axes([0.06, 0.06, 0.88, 0.84])
    ax.axis("off")
    ax.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=10, family="DejaVu Sans", color="#222", linespacing=1.35)
    filename = OUT_DIR / "00_summary.jpg"
    fig.savefig(filename, format="jpeg", dpi=150, bbox_inches="tight", pil_kwargs={"quality": 95})
    plt.close(fig)
    return filename


def draw_tags(tags):
    total_tags = Counter()
    by_tea = defaultdict(Counter)
    for tag_name, tea_order, cnt in tags:
        total_tags[tag_name] += cnt
        by_tea[tea_order][tag_name] += cnt

    top_tags = total_tags.most_common(20)
    fig, ax = plt.subplots(figsize=(11, max(6, 0.35 * max(1, len(top_tags)) + 2)), facecolor="white")
    ax.set_title("Выбранные тэги по последней дегустации", fontsize=16, fontweight="bold", pad=15)
    ax.text(0.5, 1.01, "Учитываются только участники 31 мая после 19:00 МСК и утра 1 июня", transform=ax.transAxes,
            ha="center", fontsize=10, color="#555")

    if not top_tags:
        ax.text(0.5, 0.5, "Тэгов нет", ha="center", va="center", fontsize=14)
        ax.axis("off")
    else:
        names = [x[0] for x in top_tags][::-1]
        counts = [x[1] for x in top_tags][::-1]
        y = np.arange(len(names))
        ax.barh(y, counts, color="#4E79A7", alpha=0.85)
        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=10)
        ax.set_xlabel("Количество выборов", fontsize=10)
        ax.grid(axis="x", color="#dddddd")
        ax.spines[["top", "right", "left"]].set_visible(False)
        for yi, name, count in zip(y, names, counts):
            per_tea = "; ".join(f"чай {t+1}: {by_tea[t][name]}" for t in range(5) if by_tea[t][name])
            ax.text(count + 0.05, yi, f"{count} ({per_tea})", va="center", fontsize=9)

    filename = OUT_DIR / "13_tags.jpg"
    fig.savefig(filename, format="jpeg", dpi=150, bbox_inches="tight", pil_kwargs={"quality": 95})
    plt.close(fig)
    return filename


def main():
    participants, teas, marks, tags, free_texts = get_data()
    criteria, per_criterion = build_criteria(marks)
    written = []
    written.append(draw_summary(participants, teas, criteria, per_criterion, tags, free_texts))
    for cid in sorted(criteria):
        written.append(draw_criterion_chart(criteria[cid], per_criterion[cid], len(participants)))
    written.append(draw_tags(tags))
    print("participants", len(participants))
    print("teas", len(teas))
    print("criteria", len(criteria))
    print("files")
    for path in written:
        print(path)

if __name__ == "__main__":
    main()
