# Feature Specification: Telegram Bot 2.0 (Кабинет ментора, Голосовой фидбек и Еженедельный дайджест)

## User Scenarios & Testing
- **US1 (P1)**: При отправке студентом нового ДЗ (`POST /api/v1/tasks/:id/submissions`) менторам (`Role.ADMIN` с `telegramChatId`) приходит карточка в Telegram с ссылкой на GitHub и Inline-кнопками `[ ✅ Принять (макс. балл) ]` и `[ 🔄 На доработку ]`.
- **US2 (P1)**: Ментор нажимает кнопку в Telegram — работа переводится в `ACCEPTED` (с начислением `maxScore` и ачивок) или `REVISION`, сообщение ментора обновляется, а студенту уходит уведомление.
- **US3 (P1)**: Ментор отвечает (`Reply`) на карточку ДЗ в Telegram текстом или голосовым сообщением (`voice`) — комментарий/file_id сохраняется в `Submission` (`reviewerComment` / `voiceFeedbackUrl`), а студент получает уведомление и само голосовое сообщение (`sendVoice`).
- **US4 (P1)**: Каждый понедельник в 10:00 (`0 10 * * 1`) (а также по команде `/digest` от ментора) формируется дайджест Топ-3 студентов недели и рассылается каждому привязанному студенту в Telegram (и в `TELEGRAM_COURSE_CHAT_ID`, если настроен).

## Success Criteria
- **SC-001**: Поля `mentorTelegramMsgId` и `voiceFeedbackUrl` добавлены в `Submission` (Prisma + Django Admin).
- **SC-002**: Все существующие и новые тесты проходят (`npm test`), `npx prisma validate` и `npm run build` завершаются с кодом 0.
