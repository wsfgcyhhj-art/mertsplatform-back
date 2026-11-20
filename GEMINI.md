# MertsPlatform — Инструкция проекта для Gemini

## Базовый протокол
- Всегда обращаться к пользователю: **«мой господин»** и отвечать на русском языке.
- Репозиторий **строго backend-only** (`django_admin/`, `docker-compose.yml`, `deploy/`): фронтенд живёт во внешнем репозитории; проверки ограничены Django (`manage.py check`, `manage.py test admin_panel --noinput`, `manage.py spectacular --validate --fail-on-warn`).
- Следовать правилам из `AGENTS.md`, режиму Ponytail (минимальный diff, YAGNI) и стандартам проекта.

## Silent Auto-Skills

- Никогда не жди `/slash`-команд от пользователя и не пиши отдельных сообщений/анонсов о запуске или вызове скиллов.
- Автоматически оценивай задачу и молча применяй релевантные скиллы из `.agents/skills/`, `~/.codex/skills/` и глобальных плагинов (`django-patterns`, `django-security`, `django-verification`, `postgres-patterns` — для Django/БД; `security-bounty-hunter`, `security-review`, `santa-method` — для безопасности и глубокого поиска багов; `taste`, `frontend-patterns` — для UI; `ponytail`, `grill-me`, `graphify`, `gsd` — для инженерии и навигации).
- По умолчанию на каждом запросе соблюдай сжатый стиль без воды (`caveman`, сохраняя русский язык и обращение «мой господин») и экономное чтение файлов/логов (`headroom`).
