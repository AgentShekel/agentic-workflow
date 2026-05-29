# Настройка Yandex Analytics (единый конфиг)

## Шаг 1: Создай OAuth-приложение с несколькими скоупами

1. Зайди на https://oauth.yandex.ru/client/new
2. Заполни:
   - **Название**: Claude Analytics (или любое)
   - **Платформа**: Веб-сервисы
   - **Redirect URI**: `https://oauth.yandex.ru/verification_code`
3. **Добавь ВСЕ нужные доступы:**
   - Яндекс.Вебмастер -> Получение информации о сайтах
   - Яндекс.Метрика -> Получение статистики, чтение параметров счётчика
   - Яндекс.Директ -> Управление кампаниями, Получение статистики
4. Сохрани Client ID

## Шаг 2: Получи токен

Открой в браузере:
```
https://oauth.yandex.ru/authorize?response_type=token&client_id=ТВОЙ_CLIENT_ID
```
Авторизуйся и скопируй токен из URL после `access_token=`.

## Шаг 3: Настрой дополнительные ключи

### Yandex XML Search
1. Зарегистрируйся на https://xml.yandex.ru/
2. Получи логин и API-ключ

### Yandex Maps Geosearch
1. Зайди на https://developer.tech.yandex.ru/
2. Создай API-ключ для JavaScript API и Геопоиска

### ID счётчика Metrika
1. Зайди в https://metrika.yandex.ru/
2. Скопируй ID счётчика

## Шаг 4: Заполни config/.env

```bash
# OAuth (Webmaster + Metrika + Direct)
YANDEX_OAUTH_TOKEN=y0_ваш_токен

# Metrika
YANDEX_METRIKA_COUNTER=12345678

# XML Search
YANDEX_XML_USER=ваш_логин
YANDEX_XML_KEY=ваш_ключ

# Maps/Business
YANDEX_MAPS_APIKEY=ваш_ключ

# OpenAI (для semantic drift, опционально)
# OPENAI_API_KEY=sk-...
```

## Шаг 5: Синхронизируй и проверь

```bash
# Распространить конфиг на все скиллы
bash scripts/sync-config.sh

# Проверить подключение ко всем сервисам
bash scripts/check.sh
```

## FAQ

### Один токен для всех сервисов?
Да, для Webmaster + Metrika + Direct. Создай одно OAuth-приложение с тремя скоупами.
Search XML и Maps используют свои отдельные ключи.

### А если мне нужен только Webmaster?
Заполни только `YANDEX_OAUTH_TOKEN`. Остальные поля оставь пустыми — скрипты, которым они нужны, просто выдадут предупреждение.

### Как обновить токен?
Замени `YANDEX_OAUTH_TOKEN` в `config/.env` и запусти `bash scripts/sync-config.sh`.
