import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import psycopg2


DB_URL = "postgresql://benomen:AAVolodko6872!@138.16.178.46:5432/vysota"
TASTING_ID = "32d7f152-2880-4ed6-af9d-a52036b934fb"
START_UTC = "2026-05-31 16:00:00+00"  # 19:00 MSK
END_UTC = "2026-06-01 12:00:00+00"
OUT_DIR = Path("/workspace/infographics_last_tasting_simple")

TEA_NAMES = {
    0: "Люйча\nformosensis",
    1: "Бай\nМэйжэнь",
    2: "Хунча\nformosensis",
    3: "Тайвань\nЧэн Ча",
    4: "Тяньчи\nУлун",
}

TEA_NAMES_ONE_LINE = {key: value.replace("\n", " ") for key, value in TEA_NAMES.items()}


def slugify(text: str) -> str:
    repl = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
    text = "".join(repl.get(char, char) for char in text.lower())
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:70]


def select_data():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT tp.user_id, COALESCE(NULLIF(u.first_name, ''), u.username) AS name
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

    cur.execute(
        """
        SELECT pt.id, pt."order", p.name
        FROM catalog_producttasting pt
        JOIN catalog_product p ON p.id = pt.product_id
        WHERE pt.tasting_id = %s
        ORDER BY pt."order"
        """,
        (TASTING_ID,),
    )
    teas = cur.fetchall()

    cur.execute(
        """
        SELECT tc.id,
               tc.name,
               tc.grade,
               COALESCE(tb.name, 'РАЗДЕЛ ОЦЕНКИ: органолептика заваренного чая') AS block_name,
               pt."order" AS tea_order,
               pcr.mark,
               pr.user_id
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

    cur.execute(
        """
        SELECT tt.name, pt."order", COUNT(*) AS cnt
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

    cur.execute(
        """
        SELECT pr.user_id,
               COALESCE(NULLIF(u.first_name, ''), u.username) AS name,
               COUNT(DISTINCT pr.id) AS reviews_count,
               COUNT(DISTINCT pcr.id) AS criteria_marks_count,
               COUNT(DISTINCT prtt.id) AS tags_count
        FROM catalog_productreview pr
        JOIN users_user u ON u.id = pr.user_id
        JOIN catalog_producttasting pt ON pt.id = pr.product_tasting_id
        LEFT JOIN catalog_productcriteriareview pcr ON pcr.product_review_id = pr.id
        LEFT JOIN catalog_productreview_taste_tags prtt ON prtt.productreview_id = pr.id
        WHERE pt.tasting_id = %s
          AND pr.user_id IN (
            SELECT tp.user_id
            FROM catalog_tastingparticipation tp
            WHERE tp.tasting_id = %s
              AND tp.joined_at >= TIMESTAMPTZ %s
              AND tp.joined_at <  TIMESTAMPTZ %s
          )
        GROUP BY pr.user_id, name
        ORDER BY name, pr.user_id
        """,
        (TASTING_ID, TASTING_ID, START_UTC, END_UTC),
    )
    activity = cur.fetchall()

    cur.execute(
        """
        SELECT pt."order", fp.name, fpr.text
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

    cur.execute(
        """
        SELECT pt."order", phr.template, pthr.answers
        FROM catalog_phrasetemplatereview pthr
        JOIN catalog_productreview pr ON pr.id = pthr.product_review_id
        JOIN catalog_producttasting pt ON pt.id = pr.product_tasting_id
        JOIN catalog_phrasetemplate phr ON phr.id = pthr.phrase_template_id
        WHERE pt.tasting_id = %s
          AND pr.user_id IN (
            SELECT tp.user_id
            FROM catalog_tastingparticipation tp
            WHERE tp.tasting_id = %s
              AND tp.joined_at >= TIMESTAMPTZ %s
              AND tp.joined_at <  TIMESTAMPTZ %s
          )
        ORDER BY pt."order", phr.id
        """,
        (TASTING_ID, TASTING_ID, START_UTC, END_UTC),
    )
    phrase_answers = cur.fetchall()

    cur.close()
    conn.close()
    return participants, teas, marks, tags, activity, free_texts, phrase_answers


def build_marks(marks):
    criteria = {}
    per_criterion = defaultdict(lambda: defaultdict(list))
    for cid, name, grade, block, tea_order, mark, user_id in marks:
        criteria[cid] = {"id": cid, "name": name, "grade": grade or [], "block": block}
        per_criterion[cid][tea_order].append(mark)
    return criteria, per_criterion


def save_fig(fig, filename):
    fig.tight_layout()
    fig.savefig(OUT_DIR / filename, format="jpeg", dpi=150, bbox_inches="tight", pil_kwargs={"quality": 95})
    plt.close(fig)


def draw_average_heatmap(criteria, per_criterion):
    rows = sorted(criteria)
    matrix = np.full((len(rows), 5), np.nan)
    labels = []
    for i, cid in enumerate(rows):
        labels.append(f"{cid}. {criteria[cid]['name']}")
        for tea in range(5):
            values = per_criterion[cid].get(tea, [])
            if values:
                matrix[i, tea] = float(np.mean(values))

    fig, ax = plt.subplots(figsize=(9.5, max(6, len(rows) * 0.45)), facecolor="white")
    masked = np.ma.masked_invalid(matrix)
    im = ax.imshow(masked, cmap="RdYlGn", aspect="auto")
    im.cmap.set_bad("#f2f2f2")

    ax.set_title("Средние оценки по критериям для каждого чая", fontsize=15, fontweight="bold")
    ax.set_xticks(range(5))
    ax.set_xticklabels([f"Чай {i + 1}\n{TEA_NAMES[i]}" for i in range(5)], fontsize=9)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels, fontsize=8)

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            if np.isnan(matrix[i, j]):
                ax.text(j, i, "—", ha="center", va="center", fontsize=9, color="#777")
            else:
                ax.text(j, i, f"{matrix[i, j]:.1f}", ha="center", va="center", fontsize=8)

    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.03)
    cbar.set_label("Средняя оценка")
    save_fig(fig, "01_average_scores_heatmap.jpg")


def draw_criterion_distribution(criteria_item, tea_marks):
    cid = criteria_item["id"]
    name = criteria_item["name"]
    grade = criteria_item["grade"]

    all_values = sorted({mark for values in tea_marks.values() for mark in values})
    if grade:
        grade_values = sorted({int(item["value"]) for item in grade})
        score_values = sorted(set(grade_values) | set(all_values))
    else:
        score_values = list(range(min(all_values + [0]), max(all_values + [10]) + 1))

    matrix = np.zeros((5, len(score_values)), dtype=int)
    for tea in range(5):
        counter = Counter(tea_marks.get(tea, []))
        for j, score in enumerate(score_values):
            matrix[tea, j] = counter.get(score, 0)

    fig, ax = plt.subplots(figsize=(9.6, 5.3), facecolor="white")
    im = ax.imshow(matrix, cmap="Blues", aspect="auto", vmin=0)
    ax.set_title(name, fontsize=16, fontweight="bold", pad=14)
    ax.set_xlabel("Оценка", fontsize=11)
    ax.set_ylabel("Чай", fontsize=11)
    ax.set_xticks(range(len(score_values)))
    ax.set_xticklabels([str(value) for value in score_values], fontsize=10)
    ax.set_yticks(range(5))
    ax.set_yticklabels([f"Чай {i + 1}: {TEA_NAMES_ONE_LINE[i]}" for i in range(5)], fontsize=10)

    vmax = max(1, int(matrix.max()))
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = int(matrix[i, j])
            color = "white" if value > vmax / 2 else "#222"
            ax.text(j, i, str(value) if value else "", ha="center", va="center", fontsize=13, color=color)

    ax.set_xticks(np.arange(-0.5, len(score_values), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 5, 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.2)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.spines[["top", "right", "bottom", "left"]].set_visible(False)

    filename = f"{cid:02d}_{slugify(name)}_distribution.jpg"
    save_fig(fig, filename)


def draw_top_tags(tags):
    total = Counter()
    for tag, tea, count in tags:
        total[tag] += count

    top = total.most_common(20)
    fig, ax = plt.subplots(figsize=(10, max(5, 0.35 * len(top))), facecolor="white")
    if not top:
        ax.text(0.5, 0.5, "Тэгов нет", ha="center", va="center", fontsize=14)
        ax.axis("off")
    else:
        names = [item[0] for item in top][::-1]
        counts = [item[1] for item in top][::-1]
        y = np.arange(len(names))
        ax.barh(y, counts, color="#5B8BD9")
        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=10)
        ax.set_xlabel("Количество использований")
        ax.set_title("Топ вкусовых тэгов", fontsize=15, fontweight="bold")
        ax.grid(axis="x", color="#dddddd")
        ax.spines[["top", "right", "left"]].set_visible(False)
        for yi, value in zip(y, counts):
            ax.text(value + 0.05, yi, str(value), va="center", fontsize=10)
    save_fig(fig, "02_top_tags.jpg")


def draw_tags_by_tea(tags):
    total = Counter()
    by_tea = defaultdict(Counter)
    for tag, tea, count in tags:
        total[tag] += count
        by_tea[tea][tag] += count

    selected = [tag for tag, _count in total.most_common(15)]
    matrix = np.zeros((5, len(selected)), dtype=int)
    for tea in range(5):
        for j, tag in enumerate(selected):
            matrix[tea, j] = by_tea[tea][tag]

    fig, ax = plt.subplots(figsize=(11, 5.2), facecolor="white")
    ax.imshow(matrix, cmap="Blues", aspect="auto", vmin=0)
    ax.set_title("Тэги по чаям (топ-15)", fontsize=16, fontweight="bold", pad=14)
    ax.set_xticks(range(len(selected)))
    ax.set_xticklabels(selected, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(5))
    ax.set_yticklabels([f"Чай {i + 1}: {TEA_NAMES_ONE_LINE[i]}" for i in range(5)], fontsize=9)

    vmax = max(1, int(matrix.max()) if matrix.size else 1)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = int(matrix[i, j])
            color = "white" if value > vmax / 2 else "#222"
            ax.text(j, i, str(value) if value else "", ha="center", va="center", fontsize=10, color=color)

    ax.set_xticks(np.arange(-0.5, len(selected), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 5, 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.1)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.spines[["top", "right", "bottom", "left"]].set_visible(False)
    save_fig(fig, "03_tags_by_tea_heatmap.jpg")


def draw_activity(activity):
    labels = [row[1] for row in activity]
    values = [row[3] for row in activity]
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor="white")
    x = np.arange(len(labels))
    ax.bar(x, values, color="#59A14F")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Количество оценённых критериев", fontsize=11)
    ax.set_title("Активность участников", fontsize=16, fontweight="bold", pad=14)
    ax.grid(axis="y", color="#dddddd")
    ax.spines[["top", "right"]].set_visible(False)
    save_fig(fig, "04_activity_criteria_marks.jpg")


def draw_text_comments_count(free_texts):
    counter = Counter()
    for tea, prompt, text in free_texts:
        counter[tea] += 1

    values = [counter[i] for i in range(5)]
    fig, ax = plt.subplots(figsize=(8.5, 5), facecolor="white")
    x = np.arange(5)
    ax.bar(x, values, color="#F28E2B")
    ax.set_xticks(x)
    ax.set_xticklabels([f"Чай {i + 1}\n{TEA_NAMES[i]}" for i in range(5)], fontsize=9)
    ax.set_ylabel("Количество комментариев", fontsize=11)
    ax.set_title("Свободные текстовые комментарии", fontsize=16, fontweight="bold", pad=14)
    ax.grid(axis="y", color="#dddddd")
    ax.spines[["top", "right"]].set_visible(False)
    save_fig(fig, "05_free_text_comments_by_tea.jpg")


def draw_selected_and_freeform_tags(tags, free_texts, phrase_answers):
    counts = defaultdict(lambda: defaultdict(int))

    for tag_name, tea_order, count in tags:
        counts[f"тэг: {tag_name}"][tea_order] += count

    controlled_values = {
        "не обнаружены",
        "слабо выражены",
        "хорошо заметны",
        "ярко выражены",
        "доминируют",
    }

    for tea_order, template, answers in phrase_answers:
        values = answers if isinstance(answers, list) else []
        typed_values = []
        for value in values[1:]:
            value = str(value).strip()
            if value and value.lower() not in controlled_values:
                typed_values.append(value)
        if values:
            first = str(values[0]).strip()
            if first and first.lower() not in controlled_values and len(values) <= 3:
                typed_values.insert(0, first)
        for value in typed_values:
            counts[f"своб. тэг: {value}"][tea_order] += 1

    free_text_patterns = [
        ("печенье / ваниль", ["печень", "ванил"]),
        ("пыльные / сахарные ноты", ["пыль", "сахар"]),
        ("Руби 18", ["руби 18"]),
        ("пряный", ["пряный"]),
        ("сингуц байча", ["сингуц"]),
    ]
    for tea_order, prompt_name, text in free_texts:
        lower = text.lower()
        matched = False
        for label_text, needles in free_text_patterns:
            if any(needle in lower for needle in needles):
                counts[f"текст: {label_text}"][tea_order] += 1
                matched = True
        if not matched:
            short = text.replace("\n", " ")
            if len(short) > 34:
                short = short[:31] + "..."
            counts[f"текст: {short}"][tea_order] += 1

    selected_rows = [row for row in counts if row.startswith("тэг: ")]
    typed_tag_rows = [row for row in counts if row.startswith("своб. тэг: ")]
    text_rows = [row for row in counts if row.startswith("текст: ")]
    selected_rows.sort(key=lambda row: (-sum(counts[row].values()), row))
    typed_tag_rows.sort(key=lambda row: (-sum(counts[row].values()), row))
    text_rows.sort(key=lambda row: (-sum(counts[row].values()), row))
    rows = selected_rows + typed_tag_rows + text_rows

    matrix = np.zeros((len(rows), 5), dtype=int)
    for i, row in enumerate(rows):
        for tea in range(5):
            matrix[i, tea] = counts[row][tea]

    fig, ax = plt.subplots(figsize=(10.5, max(7, len(rows) * 0.34)), facecolor="white")
    ax.imshow(matrix, cmap="Blues", aspect="auto", vmin=0)
    ax.set_title("Тэги и ручной ввод по чаям", fontsize=16, fontweight="bold", pad=14)
    ax.set_xticks(range(5))
    ax.set_xticklabels([f"Чай {i + 1}\n{TEA_NAMES[i]}" for i in range(5)], fontsize=9)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=8)
    ax.set_xlabel("Чай", fontsize=11)

    vmax = max(1, int(matrix.max()) if matrix.size else 1)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = int(matrix[i, j])
            color = "white" if value > vmax / 2 else "#222"
            ax.text(j, i, str(value) if value else "", ha="center", va="center", fontsize=9, color=color)

    ax.set_xticks(np.arange(-0.5, 5, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(rows), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.1)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.spines[["top", "right", "bottom", "left"]].set_visible(False)
    save_fig(fig, "06_tags_and_freeform_by_tea.jpg")



def criterion_label(name: str) -> str:
    replacements = {
        "Общее впечатление от сухого чайного листа": "Общее впечатление\nсухой лист",
        "Соответствие сортовым стандартам": "Сортовые\nстандарты",
        "сладость вкуса и послевкусия": "Сладость вкуса\nи послевкусия",
        "солёность / минеральность вкуса": "Солёность /\nминеральность",
        "яркость послевкусия": "Яркость\nпослевкусия",
        "выразительность аромата": "Выразительность\nаромата",
        "насыщенность цвета": "Насыщенность\nцвета",
        "плотность вкуса": "Плотность\nвкуса",
        "вкус умами": "Умами",
    }
    return replacements.get(name, name)


def draw_per_tea_criteria_heatmaps(criteria, per_criterion):
    criteria_ids = sorted(criteria)
    score_values = sorted(
        {
            score
            for cid in criteria_ids
            for tea_order in range(5)
            for score in per_criterion[cid].get(tea_order, [])
        }
        | {
            int(item["value"])
            for cid in criteria_ids
            for item in (criteria[cid].get("grade") or [])
        }
    )

    for tea_order in range(5):
        matrix = np.zeros((len(criteria_ids), len(score_values)), dtype=int)
        for i, cid in enumerate(criteria_ids):
            counter = Counter(per_criterion[cid].get(tea_order, []))
            for j, score in enumerate(score_values):
                matrix[i, j] = counter.get(score, 0)

        fig, ax = plt.subplots(figsize=(10.5, max(6.5, len(criteria_ids) * 0.48)), facecolor="white")
        ax.imshow(matrix, cmap="Blues", aspect="auto", vmin=0)
        ax.set_title(
            f"Чай {tea_order + 1}: {TEA_NAMES_ONE_LINE[tea_order]} — оценки по критериям",
            fontsize=16,
            fontweight="bold",
            pad=14,
        )
        ax.set_xlabel("Оценка", fontsize=11)
        ax.set_ylabel("Критерий", fontsize=11)
        ax.set_xticks(range(len(score_values)))
        ax.set_xticklabels([str(value) for value in score_values], fontsize=10)
        ax.set_yticks(range(len(criteria_ids)))
        ax.set_yticklabels([criterion_label(criteria[cid]["name"]) for cid in criteria_ids], fontsize=9)

        vmax = max(1, int(matrix.max()) if matrix.size else 1)
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                value = int(matrix[i, j])
                color = "white" if value > vmax / 2 else "#222"
                ax.text(j, i, str(value) if value else "", ha="center", va="center", fontsize=10, color=color)

        ax.set_xticks(np.arange(-0.5, len(score_values), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(criteria_ids), 1), minor=True)
        ax.grid(which="minor", color="white", linestyle="-", linewidth=1.1)
        ax.tick_params(which="minor", bottom=False, left=False)
        ax.spines[["top", "right", "bottom", "left"]].set_visible(False)

        filename = f"07_tea_{tea_order + 1}_all_criteria_heatmap.jpg"
        save_fig(fig, filename)


def write_readme(participants, teas, criteria, tags, free_texts):
    lines = [
        "# One-graph JPEG infographics for the May 31 tasting",
        "",
        "Every JPEG contains exactly one graph.",
        "The generator uses SELECT-only database queries.",
        "",
        f"Participants: {len(participants)}",
        f"Teas: {len(teas)}",
        f"Criteria with marks: {len(criteria)}",
        "",
        "Generated files:",
    ]
    for path in sorted(OUT_DIR.glob("*.jpg")):
        lines.append(f"- `{path.name}`")
    lines.extend(["", "Free-text comments:"])
    if free_texts:
        for tea, prompt, text in free_texts:
            short = text.replace("\n", " ")
            lines.append(f"- Tea {tea + 1}: {short}")
    else:
        lines.append("- none")
    (OUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    for path in OUT_DIR.glob("*.jpg"):
        path.unlink()

    participants, teas, marks, tags, activity, free_texts, phrase_answers = select_data()
    criteria, per_criterion = build_marks(marks)

    draw_average_heatmap(criteria, per_criterion)
    draw_top_tags(tags)
    draw_tags_by_tea(tags)
    draw_activity(activity)
    draw_text_comments_count(free_texts)
    draw_selected_and_freeform_tags(tags, free_texts, phrase_answers)

    draw_per_tea_criteria_heatmaps(criteria, per_criterion)

    for cid in sorted(criteria):
        draw_criterion_distribution(criteria[cid], per_criterion[cid])

    write_readme(participants, teas, criteria, tags, free_texts)
    print(f"participants={len(participants)} teas={len(teas)} criteria={len(criteria)}")
    for path in sorted(OUT_DIR.glob("*.jpg")):
        print(path)


if __name__ == "__main__":
    main()
