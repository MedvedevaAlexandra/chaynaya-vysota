# Финальная статистика за сегодня

Содержит только актуальную корректную статистику по последней дегустации:

- без индивидуальных графиков по каждому чаю (`07_*`);
- без графиков по проливам (`08_*`, `09_*`);
- без обычных distribution-heatmap для графиковых критериев `57`, `58`, `59`, `62`, потому что там `x` = номер пролива и несколько точек одного пользователя не являются независимыми голосами.

Фильтр участников:

```sql
tp.joined_at >= TIMESTAMPTZ '2026-05-31 16:00:00+00'
AND tp.joined_at <  TIMESTAMPTZ '2026-06-01 12:00:00+00'
```

В итоговой подборке: 14 JPEG + PDF.

Файлы:
- `01_average_scores_heatmap.jpg`
- `02_top_tags.jpg`
- `03_tags_by_tea_heatmap.jpg`
- `04_activity_criteria_marks.jpg`
- `05_free_text_comments_by_tea.jpg`
- `06_tags_and_freeform_by_tea.jpg`
- `60_obschee_vpechatlenie_ot_suhogo_chaynogo_lista_distribution.jpg`
- `61_sootvetstvie_sortovym_standartam_distribution.jpg`
- `63_terpkost_distribution.jpg`
- `64_kislotnost_distribution.jpg`
- `65_gorech_distribution.jpg`
- `66_sladost_vkusa_i_poslevkusiya_distribution.jpg`
- `67_solenost_mineralnost_vkusa_distribution.jpg`
- `68_vkus_umami_distribution.jpg`
