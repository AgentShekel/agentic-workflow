# Настройка Yandex Direct API

## Получение токена

1. Зайди на https://oauth.yandex.ru/client/new
2. Создай приложение:
   - Название: любое (например, "Claude Direct")
   - Платформа: Веб-сервисы
   - Redirect URI: `https://oauth.yandex.ru/verification_code`
   - Доступы: Яндекс.Директ → Управление кампаниями, Получение статистики
3. Сохрани `Client ID` и `Client Secret`
4. Открой в браузере:
   ```
   https://oauth.yandex.ru/authorize?response_type=token&client_id=ТВОЙ_CLIENT_ID
   ```
5. Авторизуйся и скопируй токен из URL после `access_token=`

## Песочница (для тестирования)

Для тестовых запросов можно использовать sandbox:
- Base URL: `https://api-sandbox.direct.yandex.com/json/v5/`
- Установи в `config/.env`: `YANDEX_DIRECT_SANDBOX=true`

## Настройка

Создай файл `config/.env`:

```bash
YANDEX_DIRECT_TOKEN=y0_ваш_токен
```

Для агентских аккаунтов (управление клиентами):

```bash
YANDEX_DIRECT_TOKEN=y0_ваш_токен
YANDEX_DIRECT_LOGIN=логин_клиента
```

Или установи переменные окружения:

```bash
export YANDEX_DIRECT_TOKEN=y0_ваш_токен
export YANDEX_DIRECT_LOGIN=логин_клиента  # опционально
```

## Проверка

```bash
bash scripts/quota.sh
```

Должно показать информацию об аккаунте и "Connection OK".
