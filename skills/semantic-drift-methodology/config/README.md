# Настройка Semantic Drift Analyzer

## Зависимости

### Обязательные
```bash
pip install numpy scikit-learn
```

### Для режима embeddings (опционально)
```bash
pip install sentence-transformers
```
Модель `all-MiniLM-L6-v2` (~90MB) скачается автоматически при первом запуске.
Работает локально, бесплатно, без API-ключей.

## Источники данных

### Yandex Webmaster (обязательно)
Скилл `yandex-webmaster-guide` должен быть настроен.
Данные поисковых запросов по страницам — основа анализа.

### Yandex Metrika (рекомендуется)
Скилл `yandex-metrika-guide` должен быть настроен.
Данные о трафике страниц улучшают точность internal authority.

## Быстрый старт

```bash
# 0. Resolve skills root (default ~/.claude/skills)
SKILLS_ROOT="${SKILLS_ROOT:-$HOME/.claude/skills}"

# 1. Установи зависимости
pip install numpy scikit-learn

# 2. Собери данные из Webmaster
bash "$SKILLS_ROOT"/yandex-webmaster/scripts/search_queries.sh \
  --host https://example.com --limit 500 --order TOTAL_CLICKS \
  --csv /tmp/drift_queries.csv

# 3. Запусти анализ
python "$SKILLS_ROOT"/semantic-drift/scripts/analyze.py \
  --queries /tmp/drift_queries.csv \
  --output /tmp/drift_report.html

# 4. Открой отчёт в браузере
```
