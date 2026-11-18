# Ubuntu VPS: 166.0.28.165

Требуются Docker Engine с Compose v2+, Nginx и доступ к существующей БД Neon.
Фронтенд размещается отдельно. Все команды Docker выполняются из корня репозитория.

1. Скопируйте `deploy/production.env.example` в `.env`, выполните `chmod 600 .env`
   и заполните подключение к Neon, независимые секреты и адрес фронтенда.
   `SECRET_KEY` должен содержать минимум 50 символов, JWT-секреты — минимум 32.
   Добавьте API-домен в `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS`.
2. Проверьте и запустите контейнеры:

   ```sh
   docker compose config --quiet
   docker compose up -d --build
   docker compose ps
   docker compose logs --tail=100 django_web telegram_worker node_api
   ```

   При каждом старте Django выполняются запрошенные `install_subscriptions`,
   `install_security`, `install_shop`, `migrate`, `collectstatic`. Нужна существующая
   схема Prisma; пустая БД этими командами полностью не создаётся. `install_shop`
   обновляет цены и описания стандартного каталога. До первого запуска сделайте
   резервную копию БД. Воркера и Node Compose запускает после healthcheck Django.

3. Установите конфигурацию Nginx:

   ```sh
   sudo cp deploy/nginx-mertsplatform.conf /etc/nginx/sites-available/mertsplatform
   sudo ln -sfn /etc/nginx/sites-available/mertsplatform /etc/nginx/sites-enabled/mertsplatform
   sudo nginx -t
   sudo systemctl reload nginx
   ```

   Если включён стандартный сайт Nginx, отключите его для запросов по IP.
   Добавьте свой домен в `server_name` и направьте его DNS A-запись на VPS.
   Конфиг слушает HTTP для первоначальной настройки. При `DEBUG=False` Django
   перенаправляет на HTTPS и использует Secure cookies: до использования админки
   настройте TLS, например `sudo certbot --nginx -d YOUR_API_DOMAIN` после установки
   Certbot. Для HTTPS по IP нужен доверенный сертификат с IP в SAN и HTTPS listener
   Nginx с этим сертификатом. Не подменяйте `$scheme` на `https` для обычного HTTP.
   Откройте в firewall 80/443; порты 8000/5000 доступны только на loopback VPS.

4. Входящие команды бота принимает Django webhook
   `https://YOUR_API_DOMAIN/api/v1/telegram/webhook`. Зарегистрируйте этот URL
   методом Telegram `setWebhook` с `secret_token`, равным `TELEGRAM_WEBHOOK_SECRET`.
   `deliver_telegram` непрерывно доставляет сообщения из outbox и не запускает
   polling. Не запускайте второй экземпляр доставки на старом хостинге.

`/static/` обслуживается Django WhiteNoise. Текущие медиа хранятся в Neon и
доступны по `/api/v1/media/{id}`; `/media/` проксируется согласно конфигурации,
но файлового обработчика этого пути в Django сейчас нет. Именованные volumes
сохраняют `/app/staticfiles` и `/app/media`; `docker compose down -v` удаляет их.
Для переключения `/api/` на Node используйте комментарий в конфиге; Telegram
webhook должен остаться направлен на Django отдельным exact location.
