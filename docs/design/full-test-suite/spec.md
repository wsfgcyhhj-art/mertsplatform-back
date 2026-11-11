# Feature Specification: Full Test Suite Implementation

## User Scenarios & Testing
- **US1 (P1)**: Проверка Auth & Middleware: `401` при запросе без токена или с невалидным/просроченным токеном, `403` при доступе `STUDENT` к `/api/v1/admin/*`.
- **US2 (P1)**: Проверка Tasks & Submissions: `400` при сдаче ссылки не на `github.com`, `400` при повторной отправке ДЗ, когда предыдущая попытка еще в `SENT`/`IN_REVIEW`/`ACCEPTED` (разрешено только при `REVISION`), успешный прием работы ментором (`PATCH /api/v1/admin/submissions/:id/review`) и начисление баллов.
- **US3 (P1)**: Проверка Gamification & Achievements: автоматическая выдача `WELCOME` при регистрации, `FIRST_STEP` за первое принятое ДЗ, `SCORE_20` при наборе >= 20 баллов, защита от дубликатов (идемпотентность `awardAchievement`), эндпоинт `POST /api/v1/me/claim-easter-egg`.
- **US4 (P1)**: Проверка Telegram Service: генерация ссылки привязки (`POST /api/v1/me/telegram/connect`), отвязка (`DELETE /api/v1/me/telegram/disconnect`), graceful handling `sendTelegramNotification` (отсутствие токена, блокировка бота 403).
- **US5 (P1)**: Сквозной E2E Smoke-тест (`backend/tests/e2e_flow.test.ts`): регистрация изолированного тестового студента -> проверка `WELCOME` -> сдача задания -> ревью ментором -> проверка начисления баллов и позиции в Leaderboard -> полная очистка тестовых данных.

## Success Criteria
- **SC-001**: Все 12 исходных тестов + все новые модульные, интеграционные и E2E тесты проходят на 100% (`0 fail`).
- **SC-002**: `npx prisma validate` и `npm run build` проходят без ошибок.
