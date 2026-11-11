---
description: "Rules and best practices for Node.js, Express, and Prisma in Merts Platform"
globs: ["backend/**/*.ts", "backend/**/*.js"]
---

# Node.js, Express & Prisma Guidelines for Merts Platform

## Architecture & Code Quality
- Use Express with TypeScript in strict mode.
- Avoid unnecessary wrappers and boilerplate (Ponytail minimal diff principle).
- Validate all incoming data at trust boundaries (req.body, req.query, req.params).
- Always return consistent JSON errors: `{ statusCode, error, message }`.

## Authentication & Security
- Passwords must be hashed using `bcrypt` (10 salt rounds).
- Use `accessToken` (15m expiration, sent in JSON response) and `refreshToken` (30d expiration, HttpOnly cookie with SameSite and secure).
- Role-based access control with `Role.STUDENT` and `Role.ADMIN`.
- Solution submissions must accept only valid `github.com` URLs.

## Prisma & Database
- Keep database operations parameterized through Prisma Client.
- Index lookup columns (`month`, `order`, `groupNumber`, `status`).
- Use upsert and transactions where atomicity is required.
- Do not expose sensitive data like `passwordHash` in API responses.

## Testing
- Every non-trivial business logic path (tokens, security, URLs, scoring) must be accompanied by automated tests.
- Test suites must be runnable via `npm test` using Node.js native test runner.
