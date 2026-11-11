# Implementation Plan: Full Test Suite

## Architecture & Test Suites
1. Сохранение всех 6 существующих тестовых файлов (`12` тестов):
   - `backend/tests/auth-utils.test.ts`
   - `backend/tests/errorHandler.test.ts`
   - `backend/tests/features.test.ts`
   - `backend/tests/github.test.ts`
   - `backend/tests/rbac.test.ts`
   - `backend/tests/youtube.test.ts`
2. Новые комплексные тестовые наборы:
   - `backend/tests/api-integration.test.ts` — проверка Auth & Middleware (`401`, `403`), Tasks & Submissions (валидация GitHub URL, запрет дублирующей сдачи, ревью ментором), Gamification (`WELCOME`, `FIRST_STEP`, `SCORE_20`, дедупликация, `claim-easter-egg`) и Telegram (`connect`, `disconnect`, graceful fallback).
   - `backend/tests/e2e_flow.test.ts` — сквозной E2E Smoke сценарий с полной очисткой тестовых записей в `finally`.
