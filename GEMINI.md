# MertsPlatform — Инструкция проекта для Gemini

## Базовый протокол
- Всегда обращаться к пользователю: **«мой господин»** и отвечать на русском языке.
- Репозиторий **строго backend-only** (`django_admin/`, `docker-compose.yml`, `deploy/`): фронтенд живёт во внешнем репозитории; проверки ограничены Django (`manage.py check`, `manage.py test admin_panel --noinput`, `manage.py spectacular --validate --fail-on-warn`).
- Следовать правилам из `AGENTS.md`, режиму Ponytail (минимальный diff, YAGNI) и стандартам проекта.

## Silent Auto-Skills

- Никогда не жди `/slash`-команд от пользователя и не пиши отдельных сообщений/анонсов о запуске или вызове скиллов.
- Автоматически оценивай задачу и молча применяй релевантные скиллы из `.agents/skills/`, `~/.codex/skills/` и глобальных плагинов (`django-patterns`, `django-security`, `django-verification`, `postgres-patterns` — для Django/БД; `security-bounty-hunter`, `security-review`, `santa-method` — для безопасности и глубокого поиска багов; `taste`, `frontend-patterns` — для UI; `ponytail`, `grill-me`, `graphify`, `gsd` — для инженерии и навигации).
- По умолчанию на каждом запросе соблюдай сжатый стиль без воды (`caveman`, сохраняя русский язык и обращение «мой господин») и экономное чтение файлов/логов (`headroom`).

## Автоматический релиз и деплой на VPS (обязательно после любых правок кода)

После завершения любой задачи по бэкенду или инфраструктуре агент обязан сам, без дополнительных напоминаний пользователя:
1) Прогнать `cd django_admin && ./venv/bin/python manage.py check`
2) Если менялись эндпоинты/сериализаторы — обновить `schema.yml` (`./venv/bin/python manage.py spectacular --file schema.yml --validate --fail-on-warn`)
3) Прогнать автотесты (`./venv/bin/python manage.py test admin_panel --noinput`)
4) Убедиться, что `.env` не попал в индекс, закоммитить изменения и выполнить `git push origin main`
5) Автоматически задеплоить обновление на боевой сервер:
   `ssh -o BatchMode=yes root@166.0.28.165 "cd /opt/mertsplatform && git pull --ff-only origin main && docker compose up -d --build --wait --remove-orphans"`
6) Проверить `curl -fsS https://166.0.28.165.sslip.io/api/v1/health` и отчитаться об итоговом коммите и статусе продакшена.
