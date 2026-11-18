# Ubuntu VPS: 166.0.28.165

Стек: PostgreSQL 17, Django Admin/REST API, Node Express с Telegram polling,
отдельный Django outbox worker. Фронтенд размещается отдельно. После переноса
данных подключение к Neon не используется. Требуются Docker Engine с Compose v2+,
Nginx и Bash/flock (стандартный пакет util-linux в Ubuntu).

## Подготовка окружения

Все команды выполняются из корня репозитория. Скопируйте
`deploy/production.env.example` в `.env` и выполните `chmod 600 .env`.
Задайте `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` и тот же пароль в
`DATABASE_URL=postgresql://USER:PASSWORD@db:5432/DATABASE?sslmode=disable`.
Пароль удобно создать через `openssl rand -hex 32`; специальные символы в URL
нужно percent-encode. PostgreSQL не публикует порт на хосте.

При переезде **сохраните прежний SECRET_KEY**: им зашифрованы ещё не доставленные
сообщения TelegramOutbox. Сохраните JWT-секреты, чтобы не сбросить Node-сессии.
Для новой установки генерируйте независимые секреты: `SECRET_KEY` минимум 50
символов, JWT-секреты минимум 32. Добавьте адрес фронтенда, API-домен и IP в
соответствующие `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` и CORS-настройки.
Перенесите остальные действующие переменные окружения старого сервера,
включая Telegram token и PLATFORM_OWNER_USER_ID/PLATFORM_OWNER_ADMIN_ID.

Django сохраняет явно заданный `sslmode` из URL. Без него для `db`, `localhost`,
`127.0.0.1` SSL не обязателен; для внешних хостов включается `sslmode=require`.

## Перенос Neon до первого запуска приложений

Если volume `postgres_data` уже создан PostgreSQL 16, смена тега образа на 17
не обновит его формат. Перед переключением сделайте дамп старым сервером,
сохраните volume для отката и восстановите данные в новый volume PostgreSQL 17
либо выполните отдельный `pg_upgrade`. Не подключайте каталог данных 16 к серверу 17.

1. Проверьте конфигурацию и соберите образы:

   ```sh
   docker compose config --quiet
   docker compose build
   docker compose up -d --wait db
   ```

   Приложения пока не запускайте: unmanaged-таблицы должны приехать из Neon.
   Если локальные приложения уже запущены:
   `docker compose stop django_web telegram_worker node_api`.

2. Включите режим обслуживания на старом сервере: остановите все Django/Node
   API, ботов, фоновые задачи и другие процессы, записывающие в Neon. Оставьте
   их остановленными до завершения проверки и переключения трафика. Сохраните
   старые настройки и БД для отката. Дамп содержит все схемы и данные одной БД,
   включая пользователей, уроки, сдачи, каталог и MediaAsset.

3. Запустите перенос. Нужен direct URL Neon без `-pooler` в имени хоста,
   с `sslmode=require`; не передавайте секрет в аргументах командной строки:

   ```sh
   read -rsp 'Neon direct DATABASE_URL: ' NEON_DATABASE_URL
   echo
   export NEON_DATABASE_URL
   SOURCE_WRITES_STOPPED=yes bash deploy/migrate_from_neon.sh
   unset NEON_DATABASE_URL
   ```

   Скрипт использует временные контейнеры `postgres:18-alpine` для проверки
   источника и снятия дампа, а `psql` из локального `db` (`postgres:17-alpine`)
   для восстановления. Клиенты на VPS устанавливать не нужно; Neon не изменяется.
   Скрипт отказывается при работающих локальных приложениях, непустой целевой БД
   и параллельном запуске переноса.
   Исходный `.sql`, подготовленный к восстановлению `.sql.restore` и SHA256
   обоих файлов сохраняются с правами 600 в игнорируемом `deploy/backups/`.
   Перед восстановлением удаляются системный `SET transaction_timeout` и
   ACL-команды для ролей `neon*`: `ALTER DEFAULT PRIVILEGES FOR ROLE neon…`,
   `GRANT … TO neon…`, `REVOKE … FROM neon…`. Данные COPY и тела функций
   остаются без изменений. Фильтрация завершается до запуска `psql`, поэтому
   восстановление читает готовый файл, без пайпа и ошибки broken pipe.
   Восстановление выполняется с `ON_ERROR_STOP` одной транзакцией: SQL-ошибка
   откатывает восстановление. При ошибке дампа файл может быть неполным —
   не используйте его для восстановления. Прочие ошибки требуют проверки
   перед запуском приложений; скрипт не очищает целевую БД автоматически.

   Разрешены источники до PostgreSQL 18 включительно, в том числе 16/17/18.
   Более новые версии отклоняются до дампа. Для дампа используется клиент 18
   с `--no-owner --no-acl --quote-all-identifiers`. Перенос 18 → 17 допустим
   для совместимых объектов; фильтр устраняет перечисленные служебные команды,
   но не преобразует возможности SQL, появившиеся только в PostgreSQL 18.
   Neon-specific extensions также должны поддерживаться локальным образом;
   любой оставшийся несовместимый SQL вызовет откат, а не частичный импорт.
   Сначала проверьте перенос на отдельной пустой БД.
   См. [pg_dump 18](https://www.postgresql.org/docs/18/app-pgdump.html) и
   [psql 17](https://www.postgresql.org/docs/17/app-psql.html).

4. До переключения трафика сравните число записей в исходной и новой БД
   (User, Lesson, Task, Submission, ShopProduct, ShopOrder, MediaAsset),
   выборочно проверьте пользователей, балансы, цены и историю сдач. Если есть
   файлы вне MediaAsset, перенесите их отдельно в `media_data`.

## Запуск и Telegram

Перед включением Node polling остановите прежние polling-процессы и удалите
старый webhook методом Telegram `deleteWebhook` с `drop_pending_updates=false`.
Можно вызвать метод из уже собранного образа, используя токен из `.env`:

```sh
docker compose run --rm --no-deps --entrypoint python django_web -c 'import os; import httpx; r = httpx.post("https://api.telegram.org/bot" + os.environ["TELEGRAM_BOT_TOKEN"] + "/deleteWebhook", json={"drop_pending_updates": False}); assert r.status_code == 200 and r.json().get("ok"), "deleteWebhook failed"; print("Webhook removed; pending updates retained")'
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 django_web telegram_worker node_api
```

Django ждёт готовности БД, затем выполняет `install_subscriptions`,
`install_security`, `install_shop --missing-only`, `migrate`, `collectstatic`
и запускает Gunicorn с двумя workers. Цены и описания существующих товаров
не перезаписываются. Node и worker ждут также healthcheck Django, чтобы
схема была готова. Не масштабируйте Node polling на несколько экземпляров.
`deliver_telegram` доставляет outbox постоянно; цикл проверки — 5 секунд,
неудачные отправки повторяются с задержкой. При обычном запросе Django
также пробует доставить уведомление сразу после commit.

## Nginx и HTTPS

```sh
sudo cp deploy/nginx-mertsplatform.conf /etc/nginx/sites-available/mertsplatform
sudo ln -sfn /etc/nginx/sites-available/mertsplatform /etc/nginx/sites-enabled/mertsplatform
sudo nginx -t
sudo systemctl reload nginx
```

При необходимости отключите стандартный сайт Nginx для запросов по IP.
Добавьте свой домен в `server_name` и направьте DNS A-запись на VPS.
Конфигурация слушает HTTP для первоначальной настройки. По умолчанию при
`DEBUG=False` Django перенаправляет на HTTPS и использует Secure cookies.
Для первичной настройки по `http://166.0.28.165` явно задайте в `.env`:

```dotenv
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
CSRF_TRUSTED_ORIGINS=http://166.0.28.165
```

`ALLOWED_HOSTS` уже включает IP в шаблоне. Если фронтенд также открыт по HTTP,
задайте его точный origin с портом в `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`,
`CORS_ORIGINS` и добавьте в `CSRF_TRUSTED_ORIGINS` через запятую. Сохраните
`DEBUG=False`. При отключённом Secure у CSRF-cookie используется `SameSite=Lax`,
чтобы браузер принимал cookie по HTTP. После изменения `.env` пересоздайте
контейнеры командой `docker compose up -d`. Эти три флага управляют Django.

После первичной настройки включите TLS, например
`sudo certbot --nginx -d YOUR_API_DOMAIN` после установки Certbot, и удалите
три HTTP-переопределения либо выставьте их в `True`. Обновите origins на HTTPS.
HTTP передаёт пароли и cookies без шифрования; используйте этот режим временно.
Для HTTPS по IP требуется доверенный сертификат с IP в SAN и HTTPS listener
Nginx с этим сертификатом. Не подменяйте `$scheme` на `https` для обычного HTTP.
Откройте в firewall 80/443; 8000/5000 слушают только loopback VPS.

`/api/` направлен на Django; комментарий рядом позволяет переключить его на
Express. `/static/` отдаёт WhiteNoise. `/media/` проксируется на Django, но
файлового обработчика этого пути сейчас нет: текущие медиа доступны через
`/api/v1/media/{id}` из PostgreSQL.

## Бэкапы и откат

Именованные volumes: `postgres_data`, `media_data`, `static_data`.
Не выполняйте `docker compose down -v`: это удалит данные.
Для текущего локального бэкапа, не требующего запущенного Django:

```sh
(umask 077; mkdir -p deploy/backups; docker compose exec -T db sh -ec 'export PGPASSWORD="$POSTGRES_PASSWORD"; exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl' > "deploy/backups/local-$(date -u +%Y%m%dT%H%M%SZ).sql")
```

Храните резервные копии вне VPS и проверяйте восстановление в отдельную БД.
До первых записей на новом сервере можно вернуть трафик на старый сервер и
возобновить его процессы. После появления новых данных на VPS простой откат
на старую Neon приведёт к их потере: сначала нужен обратный перенос/сверка.
