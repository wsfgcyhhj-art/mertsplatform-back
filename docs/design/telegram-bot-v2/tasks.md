# Tasks: Telegram Bot 2.0

- [x] T001 Добавить `mentorTelegramMsgId` и `voiceFeedbackUrl` в `Submission` (`schema.prisma`, БД Neon, `django_admin/admin_panel/models.py`)
- [x] T002 Установить `node-cron` и `@types/node-cron`, добавить `TELEGRAM_COURSE_CHAT_ID` в `.env` и `.env.example`
- [x] T003 Реализовать уведомление ментора с Inline-кнопками, обработчики `callback_query` и Reply (текст + войс) в `telegramService.ts` и `tasks.ts`
- [x] T004 Создать `backend/src/services/cronService.ts` для еженедельного дайджеста Топ-3 с рассылкой каждому привязанному студенту и подключить в `index.ts`
- [x] T005 Дополнить тесты, выполнить `npx prisma validate`, `npm run build`, `npm test` и перезапустить бэкенд
