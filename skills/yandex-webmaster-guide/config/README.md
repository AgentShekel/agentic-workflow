# Настройка Yandex Webmaster API

## Получение токена

1. Зайди на https://oauth.yandex.ru/client/new
2. Создай приложение:
   - Название: любое (например, "Claude Webmaster")
   - Платформа: Веб-сервисы
   - Redirect URI: `https://oauth.yandex.ru/verification_code`
   - Доступы: Яндекс.Вебмастер → Получение информации о сайтах
3. Сохрани `Client ID` и `Client Secret`
4. Открой в браузере:
   ```
   https://oauth.yandex.ru/authorize?response_type=token&client_id=ТВОЙ_CLIENT_ID
   ```
5. Авторизуйся и скопируй токен из URL после `access_token=`

## Определение HOST_ID

HOST_ID определяется автоматически при запуске скриптов.
Формат ID хоста в API: `https:example.com:443` (без двойного слэша).

Ты можешь передавать хост в обычном формате URL:
```
https://example.com
https://example.com:443
```
Скрипты сами конвертируют в формат API.

Чтобы узнать список хостов:
```bash
bash scripts/hosts.sh
```

## Настройка

Создай файл `config/.env`:

```bash
YANDEX_WEBMASTER_TOKEN=y0_ваш_токен
```

Опционально можно указать хост по умолчанию (чтобы не передавать `--host` каждый раз):

```bash
YANDEX_WEBMASTER_TOKEN=y0_ваш_токен
YANDEX_WEBMASTER_HOST=https://example.com:443
```

Или установи переменные окружения:

```bash
export YANDEX_WEBMASTER_TOKEN=y0_ваш_токен
export YANDEX_WEBMASTER_HOST=https://example.com:443
```

## Проверка

```bash
bash scripts/quota.sh
```

Должно показать user_id и список хостов с "Connection OK".
