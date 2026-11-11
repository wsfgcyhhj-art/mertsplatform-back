# Feature Specification: Интеграция Telegram-бота для персональных уведомлений студентов

## User Scenarios & Testing
- **US1 (P1)**: Студент в профиле нажимает «Подключить Telegram», переходит по ссылке `https://t.me/<bot>?start=<code>`, бот привязывает аккаунт и отправляет приветственное сообщение.
- **US2 (P1)**: Когда ментор проверяет ДЗ (`PATCH /api/v1/admin/submissions/:id/review`), студенту приходит HTML-уведомление в Telegram с названием задания, статусом, баллами и комментарием.
- **US3 (P1)**: Когда студент получает новую ачивку (`awardAchievement`), ему приходит уведомление в Telegram с названием, очками и описанием ачивки.
- **US4 (P2)**: Студент может отвязать Telegram в профиле (`DELETE /api/v1/me/telegram/disconnect`) или обновить статус привязки.

## Requirements
- **FR-001**: Поля `telegramChatId`, `telegramAuthCode`, `telegramUsername` в модели `User` Prisma и соответствующих полях в Django Admin (`models.py`).
- **FR-002**: Graceful fallback в `telegramService.ts`: при отсутствии или плейсхолдере `TELEGRAM_BOT_TOKEN` сервер не падает, а логирует предупреждение и пропускает отправку.
- **FR-003**: Защита от падения при `403 Forbidden` (если пользователь заблокировал бота) в `sendTelegramNotification`.
- **FR-004**: Блок «Уведомления в Telegram» в `ProfilePage.jsx` в палитре Dark Zinc & Amber/Emerald без фиолетовых оттенков.

## Success Criteria
- **SC-001**: `npx prisma db push`, `npx prisma validate`, `npm run build`, `npm test` проходят без ошибок.
