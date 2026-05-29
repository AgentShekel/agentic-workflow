# Настройка Yandex Metrika API

## Получение токена

1. Зайди на https://oauth.yandex.ru/client/new
2. Создай приложение:
   - Название: любое (например, "Claude Metrika")
   - Платформа: Веб-сервисы
   - Redirect URI: `https://oauth.yandex.ru/verification_code`
   - Доступы: Яндекс.Метрика → Получение статистики, чтение параметров счётчика
3. Сохрани `Client ID` и `Client Secret`
4. Открой в браузере:
   ```
   https://oauth.yandex.ru/authorize?response_type=token&client_id=ТВОЙ_CLIENT_ID
   ```
5. Авторизуйся и скопируй токен из URL после `access_token=`

## Получение ID счётчика

1. Зайди в Яндекс.Метрику: https://metrika.yandex.ru/
2. ID счётчика — число в URL или в списке счётчиков

## Настройка

Создай файл `config/.env`:

```bash
YANDEX_METRIKA_TOKEN=y0_ваш_токен
YANDEX_METRIKA_COUNTER=12345678
```

Или установи переменные окружения:

```bash
export YANDEX_METRIKA_TOKEN=y0_ваш_токен
export YANDEX_METRIKA_COUNTER=12345678
```

## Проверка

```bash
bash scripts/quota.sh
```

Должно показать название счётчика и "Connection OK".
