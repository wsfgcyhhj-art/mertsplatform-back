# Tasks: Интеграция Telegram-бота

- [x] T001 Обновить `backend/prisma/schema.prisma`, синхронизировать схему БД и обновить `django_admin/admin_panel/models.py`
- [x] T002 Установить `telegraf` в `backend/` и добавить `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` в `.env` и `.env.example`
- [x] T003 Создать `backend/src/services/telegramService.ts` и подключить инициализацию бота при старте сервера
- [x] T004 Интегрировать триггеры уведомлений в `submissions.ts`, `achievementService.ts` и роуты привязки в `me.ts`
- [x] T005 Обновить `src/pages/ProfilePage/ui/ProfilePage.jsx` (блок «Уведомления в Telegram» в стиле Dark Zinc & Amber)
- [x] T006 Проверить тесты (`npm test`), сборку (`npm run build`) и перезапустить бэкенд
