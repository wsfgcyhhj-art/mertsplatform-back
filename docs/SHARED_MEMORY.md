# SHARED_MEMORY.md — Общая память проекта MertsPlatform

> Живой операционный контекст для AI-агентов (Antigravity и Codex CLI) и разработчиков.
> **Строго без секретов:** сюда запрещено записывать пароли, токены, API-ключи, приватные ключи и `DATABASE_URL` с учётными данными.

---

## 1. Архитектура и границы репозитория

- **Режим репозитория:** строго **backend-only** (`django_admin/`, `docker-compose.yml`, `deploy/`, `AGENTS.md`, `GEMINI.md`, `docs/`). Внешний фронтенд вынесен и задеплоен отдельно (`https://mertsplatform.vercel.app`).
- **Стек (`django_admin/`):** Django 6.1 + Django REST Framework + `drf-spectacular` (OpenAPI 3.0.3 в `django_admin/schema.yml`, Swagger UI `/api/docs/`, JSON `/api/docs-json/`) + `djangorestframework-simplejwt` + `django-filter` + **Django Unfold Admin** (`/admin/`).
- **БД и кеш:** PostgreSQL 17 в Docker (`db`):
  - Legacy/основные таблицы (`User`, `StudyGroup`, `Lesson`, `Task`, `Submission`, `ScoreAdjustment`, `Achievement`, `UserAchievement`, `MonthlyScoreArchive`, `MediaAsset`, `Session`, `SubscriptionGrant`, `TelegramIdentity`, `PasswordResetTicket`, `AuthRateBucket`, `TelegramUpdate`, `TelegramOutbox`, `ShopProduct`, `ShopOrder`) имеют `managed = False` и создаются/обновляются идемпотентными management-командами на старте:
    `install_base_schema` → `install_subscriptions` → `install_security` → `install_shop --missing-only`.
  - Управляемая таблица `PlatformSetting` (`managed = True`, миграции `0001_initial`, `0002_alter_mediaasset_options_and_more`).
  - Общий распределённый кеш между воркерами Gunicorn (`--workers 2`), `telegram_worker` и `telegram_bot`: PostgreSQL `DatabaseCache` (`LOCATION: 'django_cache'`, таблица создаётся `manage.py createcachetable`); в тестах (`TESTING=True`) используется `LocMemCache`.
- **Docker Compose и Production VPS (`166.0.28.165`, `/opt/mertsplatform`):**
  - Сервисы: `db` (`postgres:17-alpine`), `django_web` (порт `127.0.0.1:8000`, за Nginx + Certbot на `https://166.0.28.165.sslip.io`), `telegram_worker` (`deliver_telegram`), `telegram_bot` (`runbot`).
- **Локальные скиллы и CLI:**
  - Установлен `graphify` (`uv tool install graphifyy`, бинарь `~/.local/bin/graphify`). Артефакты графа (`graphify-out/`) исключены из Git через `.git/info/exclude`.
  - Скиллы синхронизированы между `.agents/skills/`, `~/.gemini/config/plugins/` и `~/.codex/skills/` (`graphify`, `ponytail*`, `grill-me`, `gsd`, `taste`, `caveman`, `headroom`, `bmad`, `karpathy`, `archify`, `gstack`, `impeccable`, `matt-pocock`, `superpowers`, `agent-skills`).

---

## 2. Ключевые инженерные решения и инварианты

1. **Открытый доступ без подписок:** проверки `HasCourseAccess` удалены; доступ к урокам/заданиям/ачивкам открыт всем авторизованным пользователям (`IsAuthenticated`) в рамках их группы (`StudyGroup`) и `current_month`.
2. **Аутентификация, пароли и rate limiting:**
   - Совместимость со старыми хешами `bcrypt(raw)` и `bcrypt(sha256(raw))` с прозрачным апгрейдом на Django password hashers при входе.
   - Двойное расширение ключей `DualCaseJSONParser` (`camelCase` ↔ `snake_case`) с защитой от глубины (`max_depth=16`, `max_nodes=10000` → `400`).
   - Разделённые лимиты запросов (`AuthThrottle` для login/register/reset, `RefreshAuthThrottle` для refresh/logout) и `AUTH_TRUSTED_PROXY_HOPS=1` за Nginx.
   - Безопасный `POST /api/v1/auth/refresh` и `/logout`: `_extract_refresh_token` защищён от не-объектного/битого JSON и не-строковых токенов; `rotate_refresh`/`refresh_digest` защищены от осиротевших `Session`, naive `expires_at` и не-строк; `update_user_streak` изолирован вне транзакции ротации; при невалидном токене возвращается `401` JSON. (Профиль текущего пользователя — `GET /api/v1/users/me`).
3. **Настройки платформы (`PlatformSetting`) и медиа (`MediaAsset`):**
   - `PlatformSetting.is_public` по умолчанию `False`; чувствительные ключи (`secret`, `token`, `password`, `api_key`, `webhook`, ...) запрещены к публикации в `/api/v1/system/config` на уровне валидации и выборки.
   - Аватарки (256×256 WebP), баннеры (1600×400 WebP), иконки и фото товаров хранятся в PostgreSQL `MediaAsset` (`GET /api/v1/media/{id}`); превью в админке грузятся по URL (`loading="lazy"`), без inline base64.
4. **Telegram-интеграция и Outbox:**
   - Режим по умолчанию `TELEGRAM_MODE=polling` с автоматическим `deleteWebhook(drop_pending_updates=False)` на старте `runbot`; webhook (`/api/v1/telegram/webhook`) отклоняет запросы (`409`) вне режима `webhook` (после проверки секрета `403`).
   - Outbox (`TelegramOutbox`) с зашифрованным payload (Fernet от `SECRET_KEY`), `TELEGRAM_OUTBOX_EAGER=False` в `django_web`, доставка воркером `deliver_telegram` каждые 2 сек с `select_for_update(skip_locked=True)`. Постоянные ошибки 400/403 сразу помечаются `failed`; HTML `can't parse entities` автоматически повторяется как plain text; HTML-шаблоны `tg_template_*` валидируются при сохранении.
5. **Учебная логика, магазин, производительность и контракты API:**
   - Экономика баллов и монет магазина (`shop_balance` / `calculate_total_score` / `LeaderboardView`) считает только последнюю `ACCEPTED`-попытку на задание (`score_service.latest_accepted` / `annotate_user_scores`); повторная отправка уже принятого ДЗ отклоняется с `409 Conflict`.
   - Ревью сдачи ДЗ (`PATCH /api/v1/submissions/{id}`) защищено машиной состояний (запрет `ACCEPTED -> SENT`), проверкой оценки (`score` обязателен при `ACCEPTED` для `has_score=True`) и опциональным optimistic lock (`expectedUpdatedAt` → `409`).
   - Удаление `Task` и `Achievement` со связанными сдачами/наградами заблокировано в API (`409`) и в Unfold Admin.
   - N+1 устранены в `/api/v1/leaderboard`, `/api/v1/tasks` (`my_submissions_map`), `/api/v1/admin/users` (`annotate_user_scores`), `StudyGroupAdmin` (`Subquery`-аннотации); списки имеют верхний cap (`max_unpaginated=200`).
   - Смена группы в карточке `UserAdmin` (`group_selector`) синхронизирует `study_group` и `group_number`; массовый пересчёт баллов вычисляет реальный 1-based `final_rank`.
   - OpenAPI-схема `django_admin/schema.yml` строго типизирована по всем 46 успешным операциям без `dict`/пустых заглушек.

---

## 3. Стандартные проверки перед релизом

```bash
cd django_admin
./venv/bin/python manage.py check --deploy
./venv/bin/python manage.py makemigrations --check --dry-run
./venv/bin/python manage.py spectacular --file /tmp/schema_check.yml --validate --fail-on-warn && rm -f /tmp/schema_check.yml
DATABASE_URL="" ./venv/bin/python manage.py test admin_panel --noinput
cd .. && python3 -m unittest deploy/test_migrate_from_neon.py
```

---

## 4. Последние 15 коммитов (`git log -n 15 --shortstat`)

- `3ff8a6c` (2026-11-20) `fix(security): apply backend audit fixes AUD-001..018` — 33 files (+2847/-543): `DatabaseCache`, `install_base_schema`, `TELEGRAM_MODE`/outbox/HTML fallback, `RefreshAuthThrottle`, антидубль монет/сдач, `UserAdmin` `group_selector` + ранги, `is_public=False` + denylist, depth cap, защита удаления, state machine, фиксы N+1, типизированный OpenAPI `schema.yml`.
- `5000ea4` (2026-11-20) `feat(backend): remove frontend, fix BUG-032..035 and add dynamic admin settings` — 182 files (+2584/-27968): перевод репозитория на backend-only, удаление `src/` и `backend/`, модель `PlatformSetting`, SQL-лидерборд, парольные валидаторы.
- `38db371` (2026-11-20) `Fix StudyGroup.DoesNotExist, return user on avatar/banner upload, fix achievement icons & mobile layout, update schema.yml` — 46 files.
- `b4cc5ed` (2026-11-20) `Remove subscription restrictions and open course access for all users` — 18 files.
- `c89170c` (2026-11-19) `Fix cross-origin auth 403 and open public student registration` — 10 files.
- `fc94106` (2026-11-19) `Support PostgreSQL 17 deployment and Neon 18 dumps` — 7 files.
- `c7bd76f` (2026-11-19) `Add self-hosted PostgreSQL stack and safe Neon migration` — 10 files.
- `a40e825` (2026-11-19) `Configure VPS backend deployment with Compose and Nginx` — 8 files.
- `40a8623` (2026-11-18) `Harden login startup and database error handling` — 5 files.
- `2966c33` (2026-11-18) `Fix JSON API login without a CSRF cookie` — 8 files.
- `19d0c7b` (2026-11-18) `Allow local and Vercel CORS and restock shop` — 10 files.
- `d0d00c1` (2026-11-18) `Prevent shared footer overflow on mobile` — 1 file.
- `c8e6101` (2026-11-18) `Add Merts Shop catalog and points checkout` — 17 files.
- `464717b` (2026-11-18) `Complete Django Telegram student commands and delivery` — 19 files.
- `5dddfcf` (2026-11-18) `Improve Django Unfold admin readability and filters` — 5 files.

---

## 5. Текущий статус и открытые вопросы

- **Завершено:**
  - Фиксы аудита `AUD-001`–`AUD-018` зафиксированы и отправлены в `origin/main` (`3ff8a6c`); установлен CLI/скилл `graphify` (`0.9.113`), синхронизированы симлинки скиллов в `.agents/skills/` и `~/.codex/skills/`, настроена единая память проекта.
  - Написан блок регрессионных тестов `django_admin/admin_panel/test_audit_regressions.py` (`6d0b946`: 19 тестов поверх 74) и добавлен регрессионный тест `test_refresh_returns_401_json_and_never_500_on_invalid_inputs` в `test_security.py` (итого **94 теста** в `admin_panel` + 7 deploy-тестов); устранены баги в `StudyGroupAdmin` (ленивый fallback аннотаций), `telegram_service.py` (`cache_get_safe`/`cache_set_safe`), и `auth/refresh` (`401` JSON вместо `500` на битых/не-строковых/осиротевших токенах, `REMOTE_ADDR=None` и сбое стрика).
  - Собран локальный граф знаний `graphify-out/` (`1077 nodes`, `3066 edges`, `66 communities`; исключён из Git через `.git/info/exclude`).
- **Открыто:**
  1. Ручное применение правок на боевом VPS `166.0.28.165` (`/opt/mertsplatform`): неинтерактивный `ssh -o BatchMode=yes` возвращает `Permission denied (publickey,password)`.

---

## 6. Журнал сессий (правило обновления)

> После завершения любой нетривиальной задачи допиши 3–5 строк ниже (дата, что сделано, статус проверок, коммит, открытые вопросы — **без секретов**).

- **2026-11-23 (absolute iconUrl):** В `achievement_icons.py` добавлен расчёт абсолютного URL через `request.build_absolute_uri`, `BACKEND_PUBLIC_URL`/`SITE_URL` или фоллбэк `https://166.0.28.165.sslip.io` при `TRUST_HTTPS_PROXY=1`; подключено в `AchievementSerializer`, `AchievementsCatalogView`, `AchievementDetailView`, `UserAchievementsListView`, `award_achievement`, `get_all_media_presets_catalog`, `MediaPresetsCatalogView`, `SystemConfigView`; обновлены тесты. Проверки: `manage.py check`, `spectacular --validate --fail-on-warn` — чисто; `test admin_panel` — 94 OK (`skipped=3`). Открыто: ручной деплой на VPS.
- **2026-11-23 (achievements compat):** Добавлено дублирующее поле `isUnlockedByMe` с тем же булевым значением, что и `isUnlocked`, в `AchievementsCatalogView`, `AchievementDetailView`, `AchievementCatalogItemSerializer` (`gamification_views.py`) и `schema.yml`; добавлены ассерты в `tests.py`. Проверки: `manage.py check`, `spectacular --validate --fail-on-warn` — чисто; `test admin_panel` — 94 OK (`skipped=3`). Открыто: ручной деплой на VPS.
- **2026-11-22 (auth refresh):** Исправлен `500 Internal Server Error` на `POST /api/v1/auth/refresh` (`authentication.py`, `auth_views.py`, `throttles.py`): добавлена защита от не-объектного/битого JSON, не-строкового токена, осиротевших `Session`, naive `expires_at`, `REMOTE_ADDR=None` и сбоев `update_user_streak`; добавлен тест в `test_security.py`. Проверки: `manage.py check` / `check --deploy` (HTTPS-env) / `makemigrations --check` / `spectacular --validate --fail-on-warn` — чисто; `test admin_panel` — 94 OK (`skipped=3`), `deploy/test_migrate_from_neon.py` — 7 OK. Коммиты: `6d0b946` + фикс refresh, пуш в `origin/main`; открыт ручной деплой на VPS.
- **2026-11-22:** Добавлены 19 регрессионных тестов для `AUD-001..018` (`test_audit_regressions.py`, `6d0b946`), починен env-зависимый `test_security.py` и исправлены 2 бага в коде (`StudyGroupAdmin` N+1 из-за eager `getattr` и `cache_get_safe`/`cache_set_safe` в `telegram_service.py`). Проверки: `test admin_panel` — 93 OK (`skipped=3`), `deploy/test_migrate_from_neon.py` — 7 OK, `makemigrations --check` и `spectacular --validate --fail-on-warn` — чисто; `check --deploy` — 0 проблем с HTTPS-env. Собран граф `graphify-out/` (1077 узлов, 3066 рёбер, 66 сообществ).
- **2026-11-20:** Применены и запушены правки аудита `AUD-001..018` (`3ff8a6c`); установлен `graphifyy==0.9.113`, синхронизированы 18 плагин-скиллов + `graphify` между `.agents/skills/`, `~/.gemini/config/plugins/` и `~/.codex/skills/`; создана `docs/SHARED_MEMORY.md` и обновлена инструкция в `AGENTS.md`. VPS требует ручного `git pull && docker compose up -d --build`.
