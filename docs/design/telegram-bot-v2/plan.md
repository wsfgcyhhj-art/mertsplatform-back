# Implementation Plan: Telegram Bot 2.0

## File Changes
1. `backend/prisma/schema.prisma` & `django_admin/admin_panel/models.py` — поля `mentorTelegramMsgId` (`mentor_telegram_msg_id`) и `voiceFeedbackUrl` (`voice_feedback_url`) в `Submission`.
2. `backend/.env`, `backend/.env.example`, `backend/src/config.ts` — `TELEGRAM_COURSE_CHAT_ID`.
3. `backend/src/services/telegramService.ts` — `notifyMentorsNewSubmission`, обработчики `sub_accept:<id>`, `sub_reject:<id>`, Reply текстом и `voice`, `sendTelegramVoice`, `broadcastWeeklyDigest`.
4. `backend/src/routes/tasks.ts` — вызов `notifyMentorsNewSubmission` при создании `Submission`.
5. `backend/src/services/cronService.ts` & `backend/src/index.ts` — расписание `0 10 * * 1` через `node-cron`, агрегация Топ-3 за 7 дней и рассылка каждому студенту.
6. `backend/tests/features.test.ts` — покрытие тестами логики дайджеста и Telegram Bot 2.0.
