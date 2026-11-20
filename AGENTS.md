## Обязательный режим Ponytail

Перед любой задачей прочитай `~/.codex/skills/ponytail/SKILL.md` и применяй Ponytail Full по умолчанию. Сначала проверь существующий код, его вызовы и тесты. Следуй YAGNI и выбирай минимальный diff, который полностью решает задачу. Переиспользуй существующие решения. Не добавляй лишние обёртки, абстракции, настройки и зависимости.

## Автоактивация скиллов, Caveman и Headroom (по умолчанию)

- Автоматически и молча применяй все релевантные скиллы из `.agents/skills/` (и `~/.codex/skills/`) на каждом запросе без ожидания `/slash`-команд и без лишних объявлений.
- По умолчанию на каждом запросе держи включённым стиль **caveman** (максимально сжатые ответы без воды, сохраняя русский язык и обращение «мой господин»).
- По умолчанию на каждом запросе держи включёнными паттерны **headroom** (сжатие контекста, фильтрация длинных логов и вывод только значимых диффов).

# MertsPlatform — Инструкция и контекст проекта для Codex

## 1. Обязательный протокол работы
- Всегда обращаться к пользователю: **«мой господин»**.
- Перед любыми крупными архитектурными изменениями или миграциями БД сначала проводить аудит кода и задавать 3–5 уточняющих вопросов с вариантами и рекомендацией `[Recommended]` (протокол `grill-me`), не меняя файлы до подтверждения.
- Использовать установленные скиллы из `~/.codex/skills/` и `.agents/skills/`.

## 2. Текущая архитектура (Backend-Only: Django Ecosystem)
- **Репозиторий строго backend-only:** Весь фронтенд вынесен во внешний репозиторий (`https://mertsplatform.vercel.app`); в этом репозитории поддерживаются только `django_admin/`, `docker-compose.yml` и `deploy/`. Проверки: `manage.py check`, `manage.py test admin_panel --noinput`, `manage.py spectacular --validate --fail-on-warn`.
- **Единый бэкенд и админка (`django_admin/`):** Django 6.1 + Django REST Framework + `drf-spectacular` (Swagger `/api/docs/`, схема `/api/docs-json/`) + `djangorestframework-simplejwt` + `django-filter` + **Django Unfold Admin** (`/admin/`).
- **База данных:** PostgreSQL (`managed = False` для таблиц Prisma + `managed = True` для `PlatformSetting`). Пароли проверяются через Django hashers и legacy `bcrypt`/`sha256` (`admin_panel/authentication.py`).
- **Динамические настройки (`PlatformSetting`):** Брендинг, ссылки, правила геймификации/доступа, шаблоны и тумблеры Telegram редактируются из Unfold Admin (`/admin/`) с кешированием и отдачей публичной конфигурации через `GET /api/v1/system/config`.
- **Медиа-хранилище:** Загружаемые аватарки (256×256 WebP), баннеры (1600×400 WebP) и иконки ачивок сжимаются через Pillow и сохраняются в таблицу `MediaAsset` (`admin_panel/services/media_service.py`), отдаются по `GET /api/v1/media/{id}`.
- **Геймификация:** Динамический движок правил ачивок (`admin_panel/services/achievement_service.py` + `signals.py`) на 10 триггеров (`MANUAL`, `ON_REGISTER`, `TOTAL_SCORE`, `ACCEPTED_TASKS`, `BONUS_TASKS`, `FIRST_TRY_ACCEPTED`, `PERFECT_SCORE`, `REVISION_ACCEPTED`, `STREAK_DAYS`, `EASTER_EGG`).
- **Telegram-бот и outbox:** Гибридная схема (`admin_panel/services/telegram_service.py`, `outbox_service.py`): Webhook `POST /api/v1/telegram/webhook`, `python manage.py runbot` (сервис `telegram_bot`) и воркер `python manage.py deliver_telegram` (`telegram_worker`).
- **Docker:** `django_admin/Dockerfile`, `docker-compose.yml` (`db`, `django_web`, `telegram_worker`, `telegram_bot`), `deploy/`.

## 3. Где читать полную историю и спецификации
1. `docs/ANTIGRAVITY_HISTORY.md` — полная хронология последних 40 коммитов и изменённых файлов.
2. `specs/001-django-backend-migration/spec.md`, `plan.md`, `tasks.md` — актуальная спецификация, план и закрытые задачи миграции.
3. `.specify/memory/constitution.md` — конституция и стандарты качества кода проекта.
4. `docs/TZ.md` — исходное техническое задание платформы.
