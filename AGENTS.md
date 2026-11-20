## Обязательный режим Ponytail

Перед любой задачей прочитай `~/.codex/skills/ponytail/SKILL.md` и применяй Ponytail Full по умолчанию. Сначала проверь существующий код, его вызовы и тесты. Следуй YAGNI и выбирай минимальный diff, который полностью решает задачу. Переиспользуй существующие решения. Не добавляй лишние обёртки, абстракции, настройки и зависимости.

## Silent Auto-Skills

- Никогда не жди `/slash`-команд от пользователя и не пиши отдельных сообщений/анонсов о запуске или вызове скиллов.
- Автоматически оценивай задачу и молча применяй релевантные скиллы из `.agents/skills/`, `~/.codex/skills/` и глобальных плагинов (`django-patterns`, `django-security`, `django-verification`, `postgres-patterns` — для Django/БД; `security-bounty-hunter`, `security-review`, `santa-method` — для безопасности и глубокого поиска багов; `taste`, `frontend-patterns` — для UI; `ponytail`, `grill-me`, `graphify`, `gsd` — для инженерии и навигации).
- По умолчанию на каждом запросе соблюдай сжатый стиль без воды (`caveman`, сохраняя русский язык и обращение «мой господин») и экономное чтение файлов/логов (`headroom`).

# MertsPlatform — Инструкция и контекст проекта для Codex

## 1. Обязательный протокол работы
- Всегда обращаться к пользователю: **«мой господин»**.
- **Единая память между сессиями:** при старте любой сессии сначала прочитай `docs/SHARED_MEMORY.md`, а после завершения задачи кратко допиши туда итоги (изменения, проверки, хеш коммита) и незакрытые вопросы — строго без секретов, паролей и токенов.
- Перед любыми крупными архитектурными изменениями или миграциями БД сначала проводить аудит кода и задавать 3–5 уточняющих вопросов с вариантами и рекомендацией `[Recommended]` (протокол `grill-me`), не меняя файлы до подтверждения.
- Использовать установленные скиллы из `~/.codex/skills/` и `.agents/skills/` (включая `graphify`, `ponytail`, `caveman`, `headroom`, `grill-me`, `gsd`, `taste`).

## 2. Текущая архитектура (Backend-Only: Django Ecosystem)
- **Репозиторий строго backend-only:** Весь фронтенд вынесен во внешний репозиторий (`https://mertsplatform.vercel.app`); в этом репозитории поддерживаются только `django_admin/`, `docker-compose.yml` и `deploy/`. Проверки: `manage.py check`, `manage.py test admin_panel --noinput`, `manage.py spectacular --validate --fail-on-warn`.
- **Единый бэкенд и админка (`django_admin/`):** Django 6.1 + Django REST Framework + `drf-spectacular` (Swagger `/api/docs/`, схема `/api/docs-json/`, контракт `django_admin/schema.yml`) + `djangorestframework-simplejwt` + `django-filter` + **Django Unfold Admin** (`/admin/`).
- **База данных и общий кеш:** PostgreSQL (`managed = False` с идемпотентным bootstrap `install_base_schema` → `install_subscriptions` → `install_security` → `install_shop` + `managed = True` для `PlatformSetting`), общий `DatabaseCache` (`django_cache` через `createcachetable`). Пароли проверяются через Django hashers и legacy `bcrypt`/`sha256` (`admin_panel/authentication.py`).
- **Динамические настройки (`PlatformSetting`):** Брендинг, ссылки, правила геймификации/доступа, шаблоны и тумблеры Telegram редактируются из Unfold Admin (`/admin/`) с кешированием и отдачей публичной конфигурации через `GET /api/v1/system/config` (`is_public=False` по умолчанию).
- **Медиа-хранилище:** Загружаемые аватарки (256×256 WebP), баннеры (1600×400 WebP) и иконки ачивок сжимаются через Pillow и сохраняются в таблицу `MediaAsset` (`admin_panel/services/media_service.py`), отдаются по `GET /api/v1/media/{id}`.
- **Геймификация:** Динамический движок правил ачивок (`admin_panel/services/achievement_service.py` + `signals.py`) на 10 триггеров (`MANUAL`, `ON_REGISTER`, `TOTAL_SCORE`, `ACCEPTED_TASKS`, `BONUS_TASKS`, `FIRST_TRY_ACCEPTED`, `PERFECT_SCORE`, `REVISION_ACCEPTED`, `STREAK_DAYS`, `EASTER_EGG`).
- **Telegram-бот и outbox:** Гибридная схема (`admin_panel/services/telegram_service.py`, `outbox_service.py`): по умолчанию `TELEGRAM_MODE=polling` с `deleteWebhook` на старте (`python manage.py runbot`), `TELEGRAM_OUTBOX_EAGER=False` для `django_web` и воркер `python manage.py deliver_telegram` (каждые 2 сек), плюс webhook `POST /api/v1/telegram/webhook`.
- **Docker:** `django_admin/Dockerfile`, `docker-compose.yml` (`db`, `django_web`, `telegram_worker`, `telegram_bot`), `deploy/`.

## 3. Где читать полную историю и спецификации
1. `docs/SHARED_MEMORY.md` — оперативная архитектура, ключевые инварианты, последние 15 коммитов и журнал сессий (читать первым).
2. `docs/ANTIGRAVITY_HISTORY.md` — полная хронология предыдущих коммитов и изменённых файлов.
3. `.specify/memory/constitution.md` — конституция и стандарты качества кода проекта.
4. `docs/TZ.md` — исходное техническое задание платформы.
