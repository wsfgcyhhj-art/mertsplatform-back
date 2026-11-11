# Implementation Plan: Интеграция Telegram-бота

## Technical Context
- **Backend**: Node.js + Express + TypeScript + Prisma + `telegraf`
- **Database**: Neon PostgreSQL
- **Admin**: Django + Unfold (`django_admin/admin_panel/models.py`)
- **Frontend**: React (`src/pages/ProfilePage/ui/ProfilePage.jsx`)

## Architecture & File Changes
1. `backend/prisma/schema.prisma` — добавление `telegramChatId`, `telegramAuthCode`, `telegramUsername` в `User`.
2. `django_admin/admin_panel/models.py` и `admin.py` — синхронизация полей модели `User`.
3. `backend/.env` и `backend/.env.example` — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`.
4. `backend/src/services/telegramService.ts` — инициализация Telegraf, обработчик `/start`, `sendTelegramNotification`.
5. `backend/src/routes/submissions.ts` — отправка уведомления при проверке ДЗ.
6. `backend/src/services/achievementService.ts` — отправка уведомления при разблокировке новой ачивки.
7. `backend/src/routes/me.ts` — `POST /api/v1/me/telegram/connect`, `DELETE /api/v1/me/telegram/disconnect`, обновление `GET /api/v1/me`.
8. `src/pages/ProfilePage/ui/ProfilePage.jsx` — UI-блок подключения/отвязки Telegram с поллингом и кнопкой обновления.
