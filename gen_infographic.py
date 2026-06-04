import psycopg2
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# ── DB connection ──────────────────────────────────────────────────────────────
conn = psycopg2.connect('postgresql://benomen:AAVolodko6872!@138.16.178.46:5432/vysota')
cur = conn.cursor()

TASTING_ID = '32d7f152-2880-4ed6-af9d-a52036b934fb'
PARTICIPANT_FILTER = """
    pr.user_id IN (
        SELECT tp.user_id FROM catalog_tastingparticipation tp
        WHERE tp.tasting_id = '32d7f152-2880-4ed6-af9d-a52036b934fb'
          AND tp.joined_at >= '2026-05-31 16:00:00+00'
          AND tp.joined_at < '2026-06-01 12:00:00+00'
    )
"""

# Short product labels
SHORT_NAMES = {
    0: 'Люйча\nvar. formosensis',
    1: 'Бай Мэйжэнь',
    2: 'Хунча\nvar. formosensis',
    3: 'Тайвань\nЧэн Ча',
    4: 'Тяньчи\nЦинсинь Улун',
}

# ── 1. Participant info ────────────────────────────────────────────────────────
cur.execute(f"""
    SELECT COUNT(*) FROM catalog_tastingparticipation tp
    WHERE tp.tasting_id = '{TASTING_ID}'
      AND tp.joined_at >= '2026-05-31 16:00:00+00'
      AND tp.joined_at < '2026-06-01 12:00:00+00'
""")
n_participants = cur.fetchone()[0]

cur.execute(f"""
    SELECT COUNT(DISTINCT pr.user_id) FROM catalog_productreview pr
    JOIN catalog_producttasting pt ON pr.product_tasting_id = pt.id
    WHERE pt.tasting_id = '{TASTING_ID}'
      AND {PARTICIPANT_FILTER}
""")
n_reviewers = cur.fetchone()[0]

cur.execute(f"""
    SELECT COUNT(*) FROM catalog_productcriteriareview pcr
    JOIN catalog_productreview pr ON pr.id = pcr.product_review_id
    JOIN catalog_producttasting pt ON pr.product_tasting_id = pt.id
    WHERE pt.tasting_id = '{TASTING_ID}'
      AND {PARTICIPANT_FILTER}
""")
n_marks = cur.fetchone()[0]

# ── 2. Overall impression per product ─────────────────────────────────────────
cur.execute(f"""
    SELECT pt.order, p.name,
           ROUND(AVG(pcr.mark::numeric),2) as avg_mark,
           COUNT(pcr.mark) as n
    FROM catalog_productcriteriareview pcr
    JOIN catalog_productreview pr ON pr.id = pcr.product_review_id
    JOIN catalog_producttasting pt ON pr.product_tasting_id = pt.id
    JOIN catalog_product p ON pt.product_id = p.id
    JOIN catalog_tastecriteria tc ON pcr.criteria_id = tc.id
    WHERE pt.tasting_id = '{TASTING_ID}'
      AND tc.name = 'Общее впечатление от сухого чайного листа'
      AND {PARTICIPANT_FILTER}
    GROUP BY pt.order, p.name
    ORDER BY pt.order
""")
overall_impression = cur.fetchall()

# ── 3. All criteria per product (avg) ─────────────────────────────────────────
cur.execute(f"""
    SELECT pt.order, tc.name,
           ROUND(AVG(pcr.mark::numeric),2) as avg_mark,
           COUNT(pcr.mark) as n
    FROM catalog_productcriteriareview pcr
    JOIN catalog_productreview pr ON pr.id = pcr.product_review_id
    JOIN catalog_producttasting pt ON pr.product_tasting_id = pt.id
    JOIN catalog_tastecriteria tc ON pcr.criteria_id = tc.id
    WHERE pt.tasting_id = '{TASTING_ID}'
      AND {PARTICIPANT_FILTER}
      AND tc.name != 'Общее впечатление от сухого чайного листа'
      AND tc.name != 'Соответствие сортовым стандартам'
    GROUP BY pt.order, tc.name
    ORDER BY pt.order, tc.name
""")
criteria_data = cur.fetchall()

# ── 4. Mark distribution for "Общее впечатление" ─────────────────────────────
cur.execute(f"""
    SELECT pt.order, pcr.mark, COUNT(*) as n
    FROM catalog_productcriteriareview pcr
    JOIN catalog_productreview pr ON pr.id = pcr.product_review_id
    JOIN catalog_producttasting pt ON pr.product_tasting_id = pt.id
    JOIN catalog_tastecriteria tc ON pcr.criteria_id = tc.id
    WHERE pt.tasting_id = '{TASTING_ID}'
      AND tc.name = 'Общее впечатление от сухого чайного листа'
      AND {PARTICIPANT_FILTER}
    GROUP BY pt.order, pcr.mark
    ORDER BY pt.order, pcr.mark
""")
impression_dist = cur.fetchall()

# ── 5. Aroma phrase fill rate ─────────────────────────────────────────────────
cur.execute(f"""
    SELECT pt.order, phr.template, pthr.answers
    FROM catalog_phrasetemplatereview pthr
    JOIN catalog_productreview pr ON pr.id = pthr.product_review_id
    JOIN catalog_producttasting pt ON pr.product_tasting_id = pt.id
    JOIN catalog_phrasetemplate phr ON pthr.phrase_template_id = phr.id
    WHERE pt.tasting_id = '{TASTING_ID}'
      AND {PARTICIPANT_FILTER}
""")
phrase_rows = cur.fetchall()

# ── 6. Яркость послевкусия per product ───────────────────────────────────────
cur.execute(f"""
    SELECT pt.order,
           ROUND(AVG(pcr.mark::numeric),2) as avg_mark,
           COUNT(*) as n
    FROM catalog_productcriteriareview pcr
    JOIN catalog_productreview pr ON pr.id = pcr.product_review_id
    JOIN catalog_producttasting pt ON pr.product_tasting_id = pt.id
    JOIN catalog_tastecriteria tc ON pcr.criteria_id = tc.id
    WHERE pt.tasting_id = '{TASTING_ID}'
      AND tc.name = 'яркость послевкусия'
      AND {PARTICIPANT_FILTER}
    GROUP BY pt.order
    ORDER BY pt.order
""")
afterfeel_data = {r[0]: (float(r[1]), r[2]) for r in cur.fetchall()}

cur.close()
conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

# Colour palette (tea-inspired)
C_BG   = '#1A1A2E'
C_CARD = '#16213E'
C_ACCENT1 = '#E8C97E'  # gold
C_ACCENT2 = '#8FBC8F'  # sage green
C_ACCENT3 = '#C97B7B'  # terracotta
C_ACCENT4 = '#7B9EC9'  # dusty blue
C_ACCENT5 = '#C9A87B'  # warm amber
C_TEXT  = '#F0E6D3'
C_MUTED = '#A0957E'

PRODUCT_COLORS = [C_ACCENT2, C_ACCENT1, C_ACCENT3, C_ACCENT4, C_ACCENT5]

fig = plt.figure(figsize=(22, 28), facecolor=C_BG)
fig.subplots_adjust(left=0.04, right=0.96, top=0.96, bottom=0.03, hspace=0.50, wspace=0.35)

gs = GridSpec(5, 3, figure=fig, hspace=0.55, wspace=0.38)

# ── TITLE BLOCK ───────────────────────────────────────────────────────────────
ax_title = fig.add_subplot(gs[0, :])
ax_title.set_facecolor(C_CARD)
ax_title.set_xlim(0, 1)
ax_title.set_ylim(0, 1)
ax_title.axis('off')

ax_title.text(0.5, 0.82,
    'Дегустация 31 мая 2026 · Чайная Высота',
    ha='center', va='center', fontsize=22, fontweight='bold',
    color=C_ACCENT1, fontfamily='DejaVu Sans')
ax_title.text(0.5, 0.52,
    'Новые техники, старые корни.\nАвтохтонная камелия Тайваня',
    ha='center', va='center', fontsize=14,
    color=C_TEXT, fontfamily='DejaVu Sans')

# Stats counters
for i, (label, val) in enumerate([
    ('Участников', str(n_participants)),
    ('Оценили все 5 чаёв', str(n_reviewers)),
    ('Выставлено оценок', str(n_marks)),
    ('Чаёв на дегустации', '5'),
]):
    x = 0.12 + i * 0.24
    ax_title.text(x, 0.13, val, ha='center', va='center', fontsize=28,
                  fontweight='bold', color=C_ACCENT1)
    ax_title.text(x, -0.02, label, ha='center', va='center', fontsize=11,
                  color=C_MUTED)

# ── CHART 1: "Общее впечатление" – bar chart ─────────────────────────────────
ax1 = fig.add_subplot(gs[1, :2])
ax1.set_facecolor(C_CARD)
ax1.spines[:].set_visible(False)
ax1.tick_params(colors=C_TEXT)

orders = [r[0] for r in overall_impression]
avgs   = [float(r[2]) for r in overall_impression]
labels = [SHORT_NAMES.get(o, str(o)) for o in orders]
colors_bar = [PRODUCT_COLORS[o] for o in orders]

bars = ax1.barh(labels, avgs, color=colors_bar, height=0.55, zorder=2)
ax1.set_xlim(-3, 5)
ax1.axvline(0, color=C_MUTED, lw=1, zorder=1)

# Grade labels legend
grade_map = {-2: 'вызывает\nнеприязнь', 0: 'не впечатлил',
             1: 'ординарный', 2: 'интересный', 4: 'исключительно\nинтересный'}
for val, lab in grade_map.items():
    ax1.axvline(val, color=C_MUTED, lw=0.4, linestyle=':', zorder=0, alpha=0.6)
    ax1.text(val, len(orders) - 0.15, lab, ha='center', va='bottom', fontsize=7,
             color=C_MUTED, rotation=0)

for bar, avg, (_, _, _, n) in zip(bars, avgs, overall_impression):
    ax1.text(avg + 0.08, bar.get_y() + bar.get_height()/2,
             f'{avg:.1f}  (n={n})',
             va='center', ha='left', fontsize=10, color=C_TEXT)

ax1.set_title('Общее впечатление от сухого чайного листа (среднее)', 
              color=C_ACCENT1, fontsize=13, pad=10, fontweight='bold')
ax1.yaxis.set_tick_params(labelsize=9, labelcolor=C_TEXT)
ax1.xaxis.set_tick_params(labelsize=8, labelcolor=C_MUTED)

# ── CHART 2: Яркость послевкусия ─────────────────────────────────────────────
ax2 = fig.add_subplot(gs[1, 2])
ax2.set_facecolor(C_CARD)
ax2.spines[:].set_visible(False)
ax2.tick_params(colors=C_TEXT)

af_orders = sorted(afterfeel_data.keys())
af_avgs = [afterfeel_data[o][0] for o in af_orders]
af_labels = [SHORT_NAMES.get(o, str(o)) for o in af_orders]
af_colors = [PRODUCT_COLORS[o] for o in af_orders]

ax2.barh(af_labels, af_avgs, color=af_colors, height=0.55, zorder=2)
ax2.set_xlim(0, 10)
ax2.axvline(5, color=C_MUTED, lw=0.5, linestyle=':', zorder=0)
for i, (avg, o) in enumerate(zip(af_avgs, af_orders)):
    n = afterfeel_data[o][1]
    ax2.text(avg + 0.1, i, f'{avg:.1f} (n={n})', va='center', fontsize=9, color=C_TEXT)
ax2.set_title('Яркость послевкусия\n(среднее, шкала 0–10)', 
              color=C_ACCENT1, fontsize=12, pad=8, fontweight='bold')
ax2.yaxis.set_tick_params(labelsize=8, labelcolor=C_TEXT)
ax2.xaxis.set_tick_params(labelsize=8, labelcolor=C_MUTED)

# ── CHART 3: Radar for Бай Мэйжэнь (most data, product 1) ───────────────────
# Build criteria data for product 1
product1_criteria = {r[1]: float(r[2]) for r in criteria_data if r[0] == 1}
radar_labels = list(product1_criteria.keys())
radar_values = list(product1_criteria.values())

if radar_labels:
    ax3 = fig.add_subplot(gs[2, 0], projection='polar')
    ax3.set_facecolor(C_CARD)
    N = len(radar_labels)
    angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
    angles += angles[:1]
    vals = radar_values + [radar_values[0]]

    ax3.plot(angles, vals, color=C_ACCENT1, linewidth=2)
    ax3.fill(angles, vals, color=C_ACCENT1, alpha=0.20)
    ax3.set_xticks(angles[:-1])
    short_r = [l.replace(' / ', '/\n').replace(' вкуса и послевкусия', '\nи послевкусия') for l in radar_labels]
    ax3.set_xticklabels(short_r, size=7, color=C_TEXT)
    ax3.yaxis.set_tick_params(labelsize=6, labelcolor=C_MUTED)
    ax3.set_title('Бай Мэйжэнь\nпрофиль критериев', color=C_ACCENT1,
                  fontsize=11, pad=20, fontweight='bold')
    ax3.tick_params(colors=C_MUTED)
    ax3.spines['polar'].set_color(C_MUTED)
    ax3.grid(color=C_MUTED, alpha=0.3)

# ── CHART 4: Distribution of "Общее впечатление" marks ──────────────────────
ax4 = fig.add_subplot(gs[2, 1:])
ax4.set_facecolor(C_CARD)
ax4.spines[:].set_visible(False)

all_values = set()
dist_by_product = defaultdict(dict)
for order, mark, n in impression_dist:
    dist_by_product[order][mark] = n
    all_values.add(mark)

all_values = sorted(all_values)
grade_labels_map = {-2: '−2\nнеприязнь', 0: '0\nне впечатлил',
                     1: '1\nординарный', 2: '2\nинтересный', 4: '4\nисключит.'}

x = np.arange(len(all_values))
width = 0.14
products_with_data = sorted(dist_by_product.keys())

for i, prod_order in enumerate(products_with_data):
    heights = [dist_by_product[prod_order].get(v, 0) for v in all_values]
    offset = (i - len(products_with_data)/2 + 0.5) * width
    ax4.bar(x + offset, heights, width, color=PRODUCT_COLORS[prod_order],
            label=SHORT_NAMES.get(prod_order, str(prod_order)).replace('\n', ' '),
            zorder=2, alpha=0.9)

ax4.set_xticks(x)
ax4.set_xticklabels([grade_labels_map.get(v, str(v)) for v in all_values],
                     color=C_TEXT, fontsize=9)
ax4.yaxis.set_tick_params(labelcolor=C_MUTED, labelsize=8)
ax4.set_ylabel('Количество оценок', color=C_MUTED, fontsize=9)
ax4.set_title('Распределение оценок «Общее впечатление от сухого листа»\nпо чаям',
              color=C_ACCENT1, fontsize=12, pad=8, fontweight='bold')
legend = ax4.legend(fontsize=8, facecolor=C_CARD, labelcolor=C_TEXT,
                    framealpha=0.8, ncol=2, loc='upper right')
ax4.yaxis.grid(True, color=C_MUTED, alpha=0.2, zorder=0)
ax4.set_facecolor(C_CARD)
ax4.tick_params(axis='x', colors=C_MUTED)
ax4.tick_params(axis='y', colors=C_MUTED)
ax4.set_axisbelow(True)

# ── CHART 5: All senso criteria for product 1 (horizontal bars) ──────────────
ax5 = fig.add_subplot(gs[3, :])
ax5.set_facecolor(C_CARD)
ax5.spines[:].set_visible(False)

# Compare all sensory criteria across products that have data
# Only show criteria with data for at least one product
all_criteria = sorted(set(r[1] for r in criteria_data))
exclude = {'Общее впечатление от сухого чайного листа', 'Соответствие сортовым стандартам'}
sensory = [c for c in all_criteria if c not in exclude]

all_prods_avgs = {}
for prod_order in range(5):
    all_prods_avgs[prod_order] = {r[1]: float(r[2]) for r in criteria_data if r[0] == prod_order}

criteria_with_data = [c for c in sensory if any(c in all_prods_avgs[p] for p in range(5))]

y = np.arange(len(criteria_with_data))
bar_h = 0.14
products_in_chart = [p for p in range(5) if any(c in all_prods_avgs[p] for c in criteria_with_data)]

for i, prod_order in enumerate(products_in_chart):
    vals = [all_prods_avgs[prod_order].get(c, np.nan) for c in criteria_with_data]
    offset = (i - len(products_in_chart)/2 + 0.5) * bar_h
    bars_c = []
    for j, v in enumerate(vals):
        if not np.isnan(v):
            b = ax5.barh(y[j] + offset, v, bar_h * 0.88,
                         color=PRODUCT_COLORS[prod_order], zorder=2, alpha=0.85)
            bars_c.append(b)

ax5.set_yticks(y)
ax5.set_yticklabels(criteria_with_data, color=C_TEXT, fontsize=9)
ax5.set_xlabel('Среднее значение (шкала 0–10)', color=C_MUTED, fontsize=9)
ax5.set_title('Сенсорный профиль: сравнение критериев по всем чаям',
              color=C_ACCENT1, fontsize=13, pad=10, fontweight='bold')
ax5.xaxis.set_tick_params(labelcolor=C_MUTED, labelsize=8)
ax5.axvline(5, color=C_MUTED, lw=0.5, linestyle=':', zorder=0)

# Add legend manually
legend_patches = [mpatches.Patch(color=PRODUCT_COLORS[p],
                                  label=SHORT_NAMES.get(p,'').replace('\n',' '))
                  for p in products_in_chart]
ax5.legend(handles=legend_patches, fontsize=8, facecolor=C_CARD,
           labelcolor=C_TEXT, framealpha=0.8, loc='lower right', ncol=2)
ax5.xaxis.grid(True, color=C_MUTED, alpha=0.2, zorder=0)
ax5.set_axisbelow(True)

# ── CHART 6: Aroma phrase fill heatmap ───────────────────────────────────────
ax6 = fig.add_subplot(gs[4, :2])
ax6.set_facecolor(C_CARD)
ax6.spines[:].set_visible(False)

phrase_by_prod_cat = defaultdict(lambda: defaultdict(int))
phrase_total_by_prod = defaultdict(int)
for product_order, template, answers in phrase_rows:
    answers_list = answers if isinstance(answers, list) else json.loads(answers)
    first = answers_list[0] if answers_list else ''
    is_not_found = 'не обнаруж' in first.lower()
    has_content = any(a.strip() for a in answers_list)
    category = template.split(' {blank}')[0].strip()
    phrase_total_by_prod[product_order] += 1
    if has_content and not is_not_found:
        phrase_by_prod_cat[product_order][category] += 1

# All aroma categories
all_cats = sorted(set(cat for d in phrase_by_prod_cat.values() for cat in d))
prod_orders = sorted(phrase_by_prod_cat.keys())

if all_cats and prod_orders:
    matrix = np.zeros((len(prod_orders), len(all_cats)))
    for i, po in enumerate(prod_orders):
        total = phrase_total_by_prod.get(po, 1) / len(all_cats)  # normalize per category
        for j, cat in enumerate(all_cats):
            matrix[i, j] = phrase_by_prod_cat[po].get(cat, 0)

    im = ax6.imshow(matrix, aspect='auto', cmap='YlOrBr', vmin=0)
    ax6.set_xticks(range(len(all_cats)))
    short_cats = [c.split(',')[0][:22] for c in all_cats]
    ax6.set_xticklabels(short_cats, rotation=40, ha='right', fontsize=7.5, color=C_TEXT)
    ax6.set_yticks(range(len(prod_orders)))
    ax6.set_yticklabels([SHORT_NAMES.get(p,'').replace('\n',' ') for p in prod_orders],
                         fontsize=8, color=C_TEXT)
    for i in range(len(prod_orders)):
        for j in range(len(all_cats)):
            v = int(matrix[i, j])
            if v > 0:
                ax6.text(j, i, str(v), ha='center', va='center',
                          fontsize=9, color='#1A1A2E', fontweight='bold')
    ax6.set_title('Ароматический профиль: сколько гостей отметили тон\n(по шаблонам описания букета)',
                  color=C_ACCENT1, fontsize=12, pad=8, fontweight='bold')
    plt.colorbar(im, ax=ax6, shrink=0.6, label='Кол-во ответов').ax.yaxis.label.set_color(C_MUTED)

# ── CHART 7: Participant timeline ────────────────────────────────────────────
ax7 = fig.add_subplot(gs[4, 2])
ax7.set_facecolor(C_CARD)
ax7.spines[:].set_visible(False)

# Join times (UTC): 17:11 – 21:39 UTC = 20:11 – 00:39 Moscow
join_times_utc = [17.19, 17.19, 17.19, 17.20, 17.21, 17.23, 17.23, 17.25, 17.30, 17.79, 21.66]
join_times_msk = [t + 3 if t + 3 < 24 else t + 3 - 24 for t in join_times_utc]
# convert 0:39 -> 24.65 for sorting
join_times_msk_adj = [t if t >= 20 else t + 24 for t in join_times_msk]

bins = np.arange(19.5, 28, 0.5)
ax7.hist(join_times_msk_adj, bins=bins, color=C_ACCENT1, edgecolor=C_BG, zorder=2)
xtick_vals = [20, 21, 22, 23, 24, 25]
xtick_labs = ['20:00', '21:00', '22:00', '23:00', '00:00', '01:00']
ax7.set_xticks(xtick_vals)
ax7.set_xticklabels(xtick_labs, fontsize=8, color=C_TEXT, rotation=30)
ax7.set_ylabel('Число участников', color=C_MUTED, fontsize=9)
ax7.yaxis.set_tick_params(labelcolor=C_MUTED, labelsize=8)
ax7.set_title('Время регистрации\n(московское время)', 
              color=C_ACCENT1, fontsize=11, pad=8, fontweight='bold')
ax7.yaxis.grid(True, color=C_MUTED, alpha=0.2)
ax7.set_axisbelow(True)

# ── Final touch ───────────────────────────────────────────────────────────────
fig.text(0.5, 0.005,
         'Чайная Высота · Аналитика дегустации 31 мая 2026 · Только SELECT запросы к БД · Данные: реальные участники (вход 20:11–00:39 МСК)',
         ha='center', fontsize=8, color=C_MUTED, style='italic')

out_path = '/workspace/tasting_stats_31may.jpg'
fig.savefig(out_path, format='jpeg', dpi=130, bbox_inches='tight',
            facecolor=C_BG, pil_kwargs={'quality': 95})
plt.close(fig)
print(f'Saved: {out_path}')
