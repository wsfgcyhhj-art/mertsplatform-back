import { Express, Request, Response } from 'express';
import swaggerUi from 'swagger-ui-express';
import { getPublicOrigin } from './utils/url.js';

export const swaggerDocument = {
  openapi: '3.0.3',
  info: {
    title: 'MertsPlatform v2 API',
    version: '2.1.0',
    description:
      'Полная OpenAPI 3.0 спецификация бэкенда образовательной платформы MertsPlatform (API-First). ' +
      'Включает аутентификацию (JWT + HttpOnly Refresh Cookie), управление профилем, загрузку и раздачу медиа (аватарки, обои, пресеты), ' +
      'видеоуроки, домашние задания, отправку и ревью решений (с голосовым фидбеком из Telegram), динамический движок ачивок, лидерборд и админ-эндпоинты.',
  },
  servers: [
    {
      url: '/api/v1',
      description: 'API v1 Relative Root',
    },
  ],
  tags: [
    { name: 'Auth', description: 'Регистрация, вход, ротация JWT-токенов и выход' },
    { name: 'Profile & Users', description: 'Профиль студента, статистика, смена пароля, привязка Telegram-бота и пасхалки' },
    { name: 'Media & Presets', description: 'Загрузка файлов аватарок/баннеров (multipart/form-data), каталог пресетов и отдача медиа из БД Neon' },
    { name: 'Lessons', description: 'Видеоуроки учебной группы и месяца студента' },
    { name: 'Tasks & Submissions', description: 'Домашние задания, сдача решений на проверку и голосовой фидбек ментора' },
    { name: 'Achievements', description: 'Каталог достижений, прогресс разблокировки и системные векторные иконки' },
    { name: 'Leaderboard', description: 'Рейтинг студентов по месяцам, топ-5 и исторические архивы' },
    { name: 'Admin - Users & Scores', description: 'Управление студентами/менторами, начисление бонусов/штрафов и ручная выдача ачивок (Admin only)' },
    { name: 'Admin - Lessons & Tasks', description: 'Управление видеоуроками и учебными заданиями (Admin only)' },
    { name: 'Admin - Submissions & Leaderboard', description: 'Очередь проверки ДЗ, выставление оценок и архивация месяца (Admin only)' },
    { name: 'Health', description: 'Мониторинг состояния API, БД Neon и Telegram-бота' },
  ],
  components: {
    securitySchemes: {
      bearerAuth: {
        type: 'http',
        scheme: 'bearer',
        bearerFormat: 'JWT',
        description: 'Передайте JWT accessToken в заголовке `Authorization: Bearer <token>`',
      },
    },
    schemas: {
      ErrorResponse: {
        type: 'object',
        required: ['statusCode', 'error', 'message'],
        properties: {
          statusCode: { type: 'integer', example: 400 },
          error: { type: 'string', example: 'Bad Request' },
          message: { type: 'string', example: 'Некорректные входные данные' },
          fields: {
            type: 'object',
            additionalProperties: { type: 'string' },
            nullable: true,
            example: { login: 'Login must be at least 3 characters long' },
          },
        },
      },
      User: {
        type: 'object',
        required: ['id', 'login', 'role', 'currentMonth'],
        properties: {
          id: { type: 'string', format: 'uuid', example: 'd290f1ee-6c54-4b01-90e6-d701748f0851' },
          login: { type: 'string', example: 'student_01' },
          role: { type: 'string', enum: ['STUDENT', 'ADMIN'], example: 'STUDENT' },
          name: { type: 'string', nullable: true, example: 'Алексей Иванов' },
          telegram: { type: 'string', nullable: true, example: '@alex_ivanov' },
          telegramUsername: { type: 'string', nullable: true, example: 'alex_ivanov' },
          isTelegramConnected: { type: 'boolean', example: true },
          groupNumber: { type: 'string', nullable: true, example: '15' },
          groupId: { type: 'string', nullable: true, example: '15' },
          currentMonth: { type: 'integer', example: 1 },
          streakCount: { type: 'integer', example: 5 },
          avatarUrl: {
            type: 'string',
            nullable: true,
            example: 'https://mertsplatform-back.onrender.com/api/v1/media/presets/avatars/avatar-amber-wolf.svg',
          },
          bannerUrl: {
            type: 'string',
            nullable: true,
            example: 'https://mertsplatform-back.onrender.com/api/v1/media/presets/banners/linear-graphite.svg',
          },
          createdAt: { type: 'string', format: 'date-time' },
          updatedAt: { type: 'string', format: 'date-time' },
        },
      },
      UserStats: {
        type: 'object',
        required: ['totalScore', 'tasksAcceptedCount', 'streakCount'],
        properties: {
          totalScore: { type: 'integer', example: 145 },
          tasksAcceptedCount: { type: 'integer', example: 6 },
          streakCount: { type: 'integer', example: 5 },
        },
      },
      MediaPresetItem: {
        type: 'object',
        required: ['slug', 'title', 'url', 'path', 'dataUri'],
        properties: {
          slug: { type: 'string', example: 'linear-graphite' },
          title: { type: 'string', example: 'Linear Graphite' },
          url: {
            type: 'string',
            example: 'https://mertsplatform-back.onrender.com/api/v1/media/presets/banners/linear-graphite.svg',
          },
          path: {
            type: 'string',
            example: '/api/v1/media/presets/banners/linear-graphite.svg',
          },
          dataUri: {
            type: 'string',
            example: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmci...',
          },
        },
      },
      AchievementIconPreset: {
        type: 'object',
        required: ['slug', 'legacyKey', 'code', 'label', 'color', 'url', 'path', 'dataUri'],
        properties: {
          slug: { type: 'string', example: 'sparkles' },
          legacyKey: { type: 'string', example: 'Sparkles' },
          code: { type: 'string', example: 'WELCOME' },
          label: { type: 'string', example: 'Искры (Sparkles)' },
          color: { type: 'string', example: '#fbbf24' },
          url: {
            type: 'string',
            example: 'https://mertsplatform-back.onrender.com/api/v1/achievements/icons/sparkles.svg',
          },
          path: { type: 'string', example: '/api/v1/achievements/icons/sparkles.svg' },
          dataUri: { type: 'string', example: 'data:image/svg+xml;base64,PHN2Zy...' },
        },
      },
      LeaderboardStudent: {
        type: 'object',
        required: ['rank', 'id', 'login', 'currentMonth', 'totalScore', 'tasksSentCount', 'tasksAcceptedCount'],
        properties: {
          rank: { type: 'integer', example: 1 },
          id: { type: 'string', format: 'uuid' },
          name: { type: 'string', nullable: true, example: 'Алексей Иванов' },
          login: { type: 'string', example: 'student_01' },
          avatarUrl: {
            type: 'string',
            nullable: true,
            example: 'https://mertsplatform-back.onrender.com/api/v1/media/presets/avatars/avatar-amber-wolf.svg',
          },
          groupNumber: { type: 'string', nullable: true, example: '15' },
          currentMonth: { type: 'integer', example: 1 },
          totalScore: { type: 'integer', example: 150 },
          tasksSentCount: { type: 'integer', example: 5 },
          tasksAcceptedCount: { type: 'integer', example: 4 },
        },
      },
      Lesson: {
        type: 'object',
        required: ['id', 'title', 'videoLink', 'youtubeId', 'groupNumber', 'month', 'order'],
        properties: {
          id: { type: 'string', format: 'uuid' },
          title: { type: 'string', example: 'Урок 1: Архитектура React и состояние' },
          videoLink: { type: 'string', example: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' },
          youtubeId: { type: 'string', example: 'dQw4w9WgXcQ' },
          groupNumber: { type: 'string', example: '15' },
          month: { type: 'integer', example: 1 },
          order: { type: 'integer', example: 1 },
          createdAt: { type: 'string', format: 'date-time' },
          updatedAt: { type: 'string', format: 'date-time' },
        },
      },
      Task: {
        type: 'object',
        required: ['id', 'title', 'description', 'topic', 'month', 'order', 'hasScore', 'isBonus'],
        properties: {
          id: { type: 'string', format: 'uuid' },
          title: { type: 'string', example: 'ДЗ #1: Верстка и роутинг' },
          description: { type: 'string', example: 'Сверстать макет и настроить React Router v6' },
          topic: { type: 'string', example: 'React / TypeScript' },
          month: { type: 'integer', example: 1 },
          order: { type: 'integer', example: 1 },
          exampleLink: { type: 'string', nullable: true, example: 'https://figma.com/file/example' },
          attachmentLink: { type: 'string', nullable: true, example: 'https://github.com/merts/starter-kit' },
          hasScore: { type: 'boolean', example: true },
          maxScore: { type: 'integer', nullable: true, example: 10 },
          isBonus: { type: 'boolean', example: false },
          createdAt: { type: 'string', format: 'date-time' },
          updatedAt: { type: 'string', format: 'date-time' },
        },
      },
      Submission: {
        type: 'object',
        required: ['id', 'taskId', 'userId', 'version', 'solutionLink', 'status', 'createdAt'],
        properties: {
          id: { type: 'string', format: 'uuid' },
          taskId: { type: 'string', format: 'uuid' },
          userId: { type: 'string', format: 'uuid' },
          reviewerId: { type: 'string', format: 'uuid', nullable: true },
          version: { type: 'integer', example: 1 },
          solutionLink: { type: 'string', example: 'https://github.com/student/homework-1' },
          comment: { type: 'string', nullable: true, example: 'Выполнил основную часть и бонус' },
          status: { type: 'string', enum: ['SENT', 'IN_REVIEW', 'REVISION', 'ACCEPTED'], example: 'ACCEPTED' },
          score: { type: 'integer', nullable: true, example: 10 },
          reviewerComment: { type: 'string', nullable: true, example: 'Отличная работа, чистый код!' },
          voiceFeedbackUrl: { type: 'string', nullable: true, example: 'AwACAgIAAxkBAAI...' },
          reviewedAt: { type: 'string', format: 'date-time', nullable: true },
          createdAt: { type: 'string', format: 'date-time' },
        },
      },
      TaskWithLatestSubmission: {
        allOf: [
          { $ref: '#/components/schemas/Task' },
          {
            type: 'object',
            properties: {
              latestSubmission: {
                allOf: [{ $ref: '#/components/schemas/Submission' }],
                nullable: true,
              },
            },
          },
        ],
      },
      Achievement: {
        type: 'object',
        required: ['id', 'code', 'title', 'description', 'iconUrl', 'category', 'triggerType', 'points'],
        properties: {
          id: { type: 'string', format: 'uuid' },
          code: { type: 'string', example: 'SCORE_100' },
          title: { type: 'string', example: 'Сотка в копилке' },
          description: { type: 'string', example: 'Набрать первые 100 баллов в рейтинге' },
          iconUrl: {
            type: 'string',
            example: 'https://mertsplatform-back.onrender.com/api/v1/achievements/icons/crown.svg',
          },
          iconPath: { type: 'string', example: '/api/v1/achievements/icons/crown.svg' },
          category: {
            type: 'string',
            enum: ['START', 'TASKS', 'SCORES', 'SECRET', 'SPECIAL', 'general'],
            example: 'SCORES',
          },
          triggerType: {
            type: 'string',
            enum: [
              'MANUAL',
              'ON_REGISTER',
              'TOTAL_SCORE',
              'ACCEPTED_TASKS',
              'BONUS_TASKS',
              'FIRST_TRY_ACCEPTED',
              'PERFECT_SCORE',
              'REVISION_ACCEPTED',
              'EASTER_EGG',
            ],
            example: 'TOTAL_SCORE',
          },
          threshold: { type: 'integer', nullable: true, example: 100 },
          isActive: { type: 'boolean', example: true },
          criteria: { type: 'string', example: 'Набрать суммарно 100 баллов за принятые задания и бонусы' },
          points: { type: 'integer', example: 30 },
          unlockedCount: { type: 'integer', example: 12 },
          isUnlockedByMe: { type: 'boolean', example: true },
          unlockedAt: { type: 'string', format: 'date-time', nullable: true },
        },
      },
      AchievementDetail: {
        allOf: [
          { $ref: '#/components/schemas/Achievement' },
          {
            type: 'object',
            properties: {
              recentAchievers: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    id: { type: 'string', format: 'uuid' },
                    name: { type: 'string', nullable: true },
                    login: { type: 'string' },
                    avatarUrl: { type: 'string', nullable: true },
                    awardedAt: { type: 'string', format: 'date-time' },
                  },
                },
              },
            },
          },
        ],
      },
      ScoreAdjustment: {
        type: 'object',
        required: ['id', 'userId', 'adminId', 'amount', 'reason', 'month', 'createdAt'],
        properties: {
          id: { type: 'string', format: 'uuid' },
          userId: { type: 'string', format: 'uuid' },
          adminId: { type: 'string', format: 'uuid' },
          amount: { type: 'integer', example: 15 },
          reason: { type: 'string', example: 'Активная помощь одногруппникам на воркшопе' },
          month: { type: 'integer', example: 1 },
          createdAt: { type: 'string', format: 'date-time' },
          admin: {
            type: 'object',
            properties: {
              id: { type: 'string', format: 'uuid' },
              name: { type: 'string', nullable: true },
              login: { type: 'string' },
            },
          },
        },
      },
      HealthCheckResponse: {
        type: 'object',
        required: ['status', 'service', 'uptime', 'timestamp', 'mode', 'responseTimeMs', 'checks'],
        properties: {
          status: { type: 'string', enum: ['ok', 'degraded'], example: 'ok' },
          service: { type: 'string', example: 'merts-backend' },
          uptime: { type: 'integer', example: 3600 },
          timestamp: { type: 'string', format: 'date-time' },
          mode: { type: 'string', enum: ['shallow', 'deep'], example: 'deep' },
          responseTimeMs: { type: 'integer', example: 18 },
          checks: {
            type: 'object',
            properties: {
              database: { type: 'string', enum: ['up', 'down', 'skipped'], example: 'up' },
              telegramBot: { type: 'string', example: 'polling' },
            },
          },
        },
      },
    },
    responses: {
      BadRequestError: {
        description: 'Ошибка валидации входных параметров (400 Bad Request)',
        content: {
          'application/json': {
            schema: { $ref: '#/components/schemas/ErrorResponse' },
            example: {
              statusCode: 400,
              error: 'Bad Request',
              message: 'Проверьте корректность переданных полей',
            },
          },
        },
      },
      UnauthorizedError: {
        description: 'Не авторизован — отсутствует или просрочен JWT-токен (401 Unauthorized)',
        content: {
          'application/json': {
            schema: { $ref: '#/components/schemas/ErrorResponse' },
            example: {
              statusCode: 401,
              error: 'Unauthorized',
              message: 'Authentication token is missing or invalid',
            },
          },
        },
      },
      ForbiddenError: {
        description: 'Недостаточно прав доступа (403 Forbidden)',
        content: {
          'application/json': {
            schema: { $ref: '#/components/schemas/ErrorResponse' },
            example: {
              statusCode: 403,
              error: 'Forbidden',
              message: 'Insufficient permissions to access this resource',
            },
          },
        },
      },
      NotFoundError: {
        description: 'Запрашиваемый ресурс не найден (404 Not Found)',
        content: {
          'application/json': {
            schema: { $ref: '#/components/schemas/ErrorResponse' },
            example: {
              statusCode: 404,
              error: 'Not Found',
              message: 'Resource not found',
            },
          },
        },
      },
      ConflictError: {
        description: 'Конфликт уникальности данных (409 Conflict)',
        content: {
          'application/json': {
            schema: { $ref: '#/components/schemas/ErrorResponse' },
            example: {
              statusCode: 409,
              error: 'Conflict',
              message: 'Resource already exists',
            },
          },
        },
      },
    },
  },
  security: [{ bearerAuth: [] }],
  paths: {
    // ──────────────────────────────────────────────────────────────────────────
    // AUTH
    // ──────────────────────────────────────────────────────────────────────────
    '/auth/register': {
      post: {
        tags: ['Auth'],
        summary: 'Регистрация нового студента',
        description:
          'Создает аккаунт студента, автоматически начисляет приветственную ачивку (ON_REGISTER / WELCOME), ставит HttpOnly cookie `refreshToken` и возвращает `accessToken`.',
        security: [],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['login', 'password', 'groupNumber'],
                properties: {
                  login: { type: 'string', minLength: 3, example: 'student_01' },
                  password: { type: 'string', minLength: 8, example: 'SecretPass123' },
                  groupNumber: { type: 'string', example: '15' },
                  name: { type: 'string', example: 'Алексей Иванов' },
                  telegram: { type: 'string', example: '@alex_ivanov' },
                  groupId: { type: 'string', example: '15' },
                  currentMonth: { type: 'integer', default: 1, example: 1 },
                },
              },
            },
          },
        },
        responses: {
          201: {
            description: 'Студент успешно зарегистрирован',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['accessToken', 'user'],
                  properties: {
                    accessToken: { type: 'string', example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...' },
                    user: { $ref: '#/components/schemas/User' },
                    awardedAchievement: {
                      allOf: [{ $ref: '#/components/schemas/Achievement' }],
                      nullable: true,
                    },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          409: { $ref: '#/components/responses/ConflictError' },
        },
      },
    },
    '/auth/login': {
      post: {
        tags: ['Auth'],
        summary: 'Вход в систему по логину и паролю',
        description: 'Проверяет учетные данные, обновляет дневной стрик, устанавливает HttpOnly cookie `refreshToken` и возвращает `accessToken` + профиль.',
        security: [],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['login', 'password'],
                properties: {
                  login: { type: 'string', example: 'student_01' },
                  password: { type: 'string', example: 'SecretPass123' },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Успешный вход',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['accessToken', 'user'],
                  properties: {
                    accessToken: { type: 'string', example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...' },
                    user: { $ref: '#/components/schemas/User' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/auth/refresh': {
      post: {
        tags: ['Auth'],
        summary: 'Ротация токенов по HttpOnly cookie refreshToken',
        security: [],
        responses: {
          200: {
            description: 'Выпущен новый accessToken и обновлена cookie refreshToken',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['accessToken'],
                  properties: {
                    accessToken: { type: 'string', example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...' },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/auth/logout': {
      post: {
        tags: ['Auth'],
        summary: 'Выход и удаление сессии',
        security: [],
        responses: {
          200: {
            description: 'Сессия завершена и cookie очищена',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    message: { type: 'string', example: 'Logged out successfully' },
                  },
                },
              },
            },
          },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // PROFILE & USERS (/me & /users/me)
    // ──────────────────────────────────────────────────────────────────────────
    '/me': {
      get: {
        tags: ['Profile & Users'],
        summary: 'Профиль текущего пользователя со статистикой и статусом Telegram',
        description: 'Доступен также по алиасу `GET /api/v1/users/me`. Возвращает профиль с полными URL аватара и баннера.',
        responses: {
          200: {
            description: 'Данные текущего пользователя и счетчики баллов/задач/стрика',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['user', 'isTelegramConnected', 'stats'],
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                    isTelegramConnected: { type: 'boolean', example: true },
                    telegramUsername: { type: 'string', nullable: true, example: 'alex_ivanov' },
                    stats: { $ref: '#/components/schemas/UserStats' },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/users/me/profile': {
      patch: {
        tags: ['Profile & Users'],
        summary: 'Частичное обновление профиля пользователя (имя, Telegram)',
        description: 'Доступен также по алиасу `PATCH /api/v1/me/profile`. Обновляет `name` и/или `telegram`. Смена группы студентом запрещена.',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                properties: {
                  name: { type: 'string', nullable: true, example: 'Алексей Иванов' },
                  telegram: { type: 'string', nullable: true, example: '@alex_ivanov' },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Профиль успешно обновлен',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['user'],
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/me/change-password': {
      post: {
        tags: ['Profile & Users'],
        summary: 'Смена пароля текущего пользователя',
        description: 'Доступен также по алиасу `POST /api/v1/users/me/change-password`.',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['currentPassword', 'newPassword'],
                properties: {
                  currentPassword: { type: 'string', example: 'OldPass123' },
                  newPassword: { type: 'string', minLength: 4, example: 'NewSecretPass456' },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Пароль успешно изменен',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    statusCode: { type: 'integer', example: 200 },
                    message: { type: 'string', example: 'Password changed successfully' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/me/achievements': {
      get: {
        tags: ['Profile & Users', 'Achievements'],
        summary: 'Список полученных ачивок текущего студента',
        description: 'Доступен также по алиасу `GET /api/v1/users/me/achievements`.',
        responses: {
          200: {
            description: 'Массив разблокированных студентом ачивок с датой награждения',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['total', 'achievements'],
                  properties: {
                    total: { type: 'integer', example: 3 },
                    achievements: {
                      type: 'array',
                      items: {
                        allOf: [
                          { $ref: '#/components/schemas/Achievement' },
                          {
                            type: 'object',
                            properties: {
                              awardedAt: { type: 'string', format: 'date-time' },
                            },
                          },
                        ],
                      },
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/me/claim-easter-egg': {
      post: {
        tags: ['Profile & Users', 'Achievements'],
        summary: 'Активация секретной пасхалки (триггер EASTER_EGG)',
        description: 'Начисляет секретную ачивку при клике по спрятанному элементу в UI.',
        responses: {
          200: {
            description: 'Результат активации пасхалки',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['success', 'alreadyUnlocked'],
                  properties: {
                    success: { type: 'boolean', example: true },
                    alreadyUnlocked: { type: 'boolean', example: false },
                    achievement: {
                      allOf: [{ $ref: '#/components/schemas/Achievement' }],
                      nullable: true,
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/me/telegram/connect': {
      post: {
        tags: ['Profile & Users'],
        summary: 'Генерация персональной ссылки для привязки Telegram-бота (@MertsPlatform_bot)',
        description:
          'Генерирует одноразовый 16-символьный код `telegramAuthCode` и возвращает deep-link `https://t.me/MertsPlatform_bot?start=<code>`.',
        responses: {
          200: {
            description: 'Ссылка для перехода в Telegram-бот',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['link'],
                  properties: {
                    link: {
                      type: 'string',
                      example: 'https://t.me/MertsPlatform_bot?start=a1b2c3d4e5f60718',
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/me/telegram/disconnect': {
      delete: {
        tags: ['Profile & Users'],
        summary: 'Отвязка Telegram-бота от профиля студента',
        responses: {
          200: {
            description: 'Telegram успешно отвязан',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['success', 'isTelegramConnected'],
                  properties: {
                    success: { type: 'boolean', example: true },
                    isTelegramConnected: { type: 'boolean', example: false },
                    telegramUsername: { type: 'string', nullable: true, example: null },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // MEDIA & PRESETS
    // ──────────────────────────────────────────────────────────────────────────
    '/users/me/avatar': {
      post: {
        tags: ['Media & Presets', 'Profile & Users'],
        summary: 'Загрузка файла аватарки студента (multipart/form-data)',
        description:
          'Доступен также по `POST /api/v1/me/avatar`. Принимает изображение (JPEG, PNG, WebP, GIF, SVG до 2 МБ), конвертирует через `sharp` в `256×256 WebP` (quality 85), сохраняет в таблицу `MediaAsset` БД Neon и возвращает полный публичный URL.',
        requestBody: {
          required: true,
          content: {
            'multipart/form-data': {
              schema: {
                type: 'object',
                required: ['file'],
                properties: {
                  file: {
                    type: 'string',
                    format: 'binary',
                    description: 'Файл аватарки (JPEG, PNG, WebP, GIF, SVG до 2 МБ)',
                  },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Аватар успешно загружен, оптимизирован и сохранен в БД Neon',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['user', 'avatarUrl', 'assetId'],
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                    avatarUrl: {
                      type: 'string',
                      example: 'https://mertsplatform-back.onrender.com/api/v1/media/3fa85f64-5717-4562-b3fc-2c963f66afa6',
                    },
                    avatarPath: {
                      type: 'string',
                      example: '/api/v1/media/3fa85f64-5717-4562-b3fc-2c963f66afa6',
                    },
                    assetId: { type: 'string', format: 'uuid' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
      patch: {
        tags: ['Media & Presets', 'Profile & Users'],
        summary: 'Установка пресета аватарки по URL или сброс (null)',
        description: 'Доступен также по `PATCH /api/v1/me/avatar`. Устанавливает URL пресета из `/api/v1/media/presets` или сбрасывает аватар в `null`.',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['avatarUrl'],
                properties: {
                  avatarUrl: {
                    type: 'string',
                    nullable: true,
                    example: '/api/v1/media/presets/avatars/avatar-amber-wolf.svg',
                  },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Аватар успешно обновлен',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['user'],
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/users/me/banner': {
      post: {
        tags: ['Media & Presets', 'Profile & Users'],
        summary: 'Загрузка файла обоев/баннера профиля (multipart/form-data)',
        description:
          'Доступен также по `POST /api/v1/me/banner`. Принимает файл обложки (JPEG, PNG, WebP, GIF, SVG до 5 МБ), конвертирует через `sharp` в `1600×400 WebP` (quality 85), сохраняет в таблицу `MediaAsset` БД Neon и возвращает полный публичный URL.',
        requestBody: {
          required: true,
          content: {
            'multipart/form-data': {
              schema: {
                type: 'object',
                required: ['file'],
                properties: {
                  file: {
                    type: 'string',
                    format: 'binary',
                    description: 'Файл баннера профиля (JPEG, PNG, WebP, GIF, SVG до 5 МБ)',
                  },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Баннер успешно загружен, оптимизирован и сохранен в БД Neon',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['user', 'bannerUrl', 'assetId'],
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                    bannerUrl: {
                      type: 'string',
                      example: 'https://mertsplatform-back.onrender.com/api/v1/media/7b29c4a1-9123-4bc1-8890-12a4567890ef',
                    },
                    bannerPath: {
                      type: 'string',
                      example: '/api/v1/media/7b29c4a1-9123-4bc1-8890-12a4567890ef',
                    },
                    assetId: { type: 'string', format: 'uuid' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
      patch: {
        tags: ['Media & Presets', 'Profile & Users'],
        summary: 'Установка пресета баннера профиля по URL или сброс (null)',
        description: 'Доступен также по `PATCH /api/v1/me/banner`. Устанавливает URL пресета из `/api/v1/media/presets` или сбрасывает баннер в `null`.',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['bannerUrl'],
                properties: {
                  bannerUrl: {
                    type: 'string',
                    nullable: true,
                    example: '/api/v1/media/presets/banners/linear-graphite.svg',
                  },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Баннер успешно обновлен',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['user'],
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/media/presets': {
      get: {
        tags: ['Media & Presets'],
        summary: 'Каталог фирменных обоев профиля, дефолтных аватаров и пресетов иконок ачивок',
        security: [],
        responses: {
          200: {
            description: 'Готовые каталоги баннеров (6), аватаров (6) и иконок ачивок (12) с абсолютными URL и Data URI',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['banners', 'avatars', 'achievementIcons'],
                  properties: {
                    banners: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/MediaPresetItem' },
                    },
                    avatars: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/MediaPresetItem' },
                    },
                    achievementIcons: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/AchievementIconPreset' },
                    },
                  },
                },
              },
            },
          },
        },
      },
    },
    '/media/presets/banners/{slug}': {
      get: {
        tags: ['Media & Presets'],
        summary: 'Отдача векторного SVG-баннера профиля по slug',
        security: [],
        parameters: [
          {
            name: 'slug',
            in: 'path',
            required: true,
            schema: { type: 'string', example: 'linear-graphite.svg' },
          },
        ],
        responses: {
          200: {
            description: 'SVG-изображение баннера (image/svg+xml)',
            content: { 'image/svg+xml': { schema: { type: 'string' } } },
          },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/media/presets/avatars/{slug}': {
      get: {
        tags: ['Media & Presets'],
        summary: 'Отдача векторного SVG-аватара по slug',
        security: [],
        parameters: [
          {
            name: 'slug',
            in: 'path',
            required: true,
            schema: { type: 'string', example: 'avatar-amber-wolf.svg' },
          },
        ],
        responses: {
          200: {
            description: 'SVG-изображение аватара (image/svg+xml)',
            content: { 'image/svg+xml': { schema: { type: 'string' } } },
          },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/media/{id}': {
      get: {
        tags: ['Media & Presets'],
        summary: 'Персистентная отдача загруженного медиафайла (WebP/SVG/GIF) из БД Neon',
        security: [],
        parameters: [
          {
            name: 'id',
            in: 'path',
            required: true,
            schema: { type: 'string', format: 'uuid' },
            description: 'UUID медиафайла из таблицы MediaAsset',
          },
        ],
        responses: {
          200: {
            description: 'Бинарный поток изображения с заголовком Cache-Control: public, max-age=31536000, immutable',
            content: {
              'image/webp': { schema: { type: 'string', format: 'binary' } },
              'image/svg+xml': { schema: { type: 'string' } },
              'image/gif': { schema: { type: 'string', format: 'binary' } },
            },
          },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // LESSONS
    // ──────────────────────────────────────────────────────────────────────────
    '/lessons': {
      get: {
        tags: ['Lessons'],
        summary: 'Список видеоуроков группы студента (с поддержкой просмотра пройденных месяцев)',
        parameters: [
          {
            name: 'month',
            in: 'query',
            required: false,
            schema: { type: 'string', example: '1' },
            description: 'Номер месяца (1..currentMonth) или `all` для всех доступных студенту месяцев',
          },
          {
            name: 'groupNumber',
            in: 'query',
            required: false,
            schema: { type: 'string', example: '15' },
            description: 'Фильтр по группе (только для роли ADMIN)',
          },
        ],
        responses: {
          200: {
            description: 'Массив уроков с метаданными текущего месяца и группы',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['month', 'currentMonth', 'lessons'],
                  properties: {
                    month: { oneOf: [{ type: 'integer' }, { type: 'string' }], example: 1 },
                    currentMonth: { type: 'integer', example: 1 },
                    groupNumber: { type: 'string', nullable: true, example: '15' },
                    lessons: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/Lesson' },
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // TASKS & SUBMISSIONS
    // ──────────────────────────────────────────────────────────────────────────
    '/tasks': {
      get: {
        tags: ['Tasks & Submissions'],
        summary: 'Список заданий текущего месяца студента со статусом последней сдачи (latestSubmission)',
        parameters: [
          {
            name: 'month',
            in: 'query',
            required: false,
            schema: { type: 'integer', example: 1 },
            description: 'Номер месяца (для ADMIN позволяет просматривать любой месяц)',
          },
        ],
        responses: {
          200: {
            description: 'Список заданий месяца',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['month', 'tasks'],
                  properties: {
                    month: { type: 'integer', example: 1 },
                    tasks: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/TaskWithLatestSubmission' },
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/tasks/{id}': {
      get: {
        tags: ['Tasks & Submissions'],
        summary: 'Детальная карточка задания с полной историей попыток сдачи студента',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        responses: {
          200: {
            description: 'Карточка задания и массив submissions',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['task'],
                  properties: {
                    task: {
                      allOf: [
                        { $ref: '#/components/schemas/Task' },
                        {
                          type: 'object',
                          properties: {
                            submissions: {
                              type: 'array',
                              items: { $ref: '#/components/schemas/Submission' },
                            },
                          },
                        },
                      ],
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/tasks/{id}/submissions': {
      post: {
        tags: ['Tasks & Submissions'],
        summary: 'Отправка решения ДЗ студентом (ссылка на GitHub)',
        description:
          'Повторная отправка разрешена только если предыдущая попытка получила статус `REVISION`. Отправляет карточку ментору в Telegram и обновляет стрик.',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['solutionLink'],
                properties: {
                  solutionLink: { type: 'string', example: 'https://github.com/student/homework-1' },
                  comment: { type: 'string', nullable: true, example: 'Готово к проверке!' },
                },
              },
            },
          },
        },
        responses: {
          201: {
            description: 'Решение принято в очередь на проверку',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['submission', 'streakCount'],
                  properties: {
                    submission: { $ref: '#/components/schemas/Submission' },
                    streakCount: { type: 'integer', example: 4 },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          401: { $ref: '#/components/responses/UnauthorizedError' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/submissions/{id}/voice': {
      get: {
        tags: ['Tasks & Submissions'],
        summary: 'Стриминг голосового фидбека ментора из Telegram (audio/ogg)',
        description: 'Доступен только автору решения или администратору/ментору. Поддерживает `Accept-Ranges: bytes`.',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        responses: {
          200: {
            description: 'Аудиопоток голосового ревью (audio/ogg)',
            content: {
              'audio/ogg': { schema: { type: 'string', format: 'binary' } },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
          403: { $ref: '#/components/responses/ForbiddenError' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // ACHIEVEMENTS
    // ──────────────────────────────────────────────────────────────────────────
    '/achievements': {
      get: {
        tags: ['Achievements'],
        summary: 'Каталог всех активных ачивок платформы со статусом разблокировки для текущего студента',
        responses: {
          200: {
            description: 'Массив активных ачивок с полными URL иконок, правилами и прогрессом',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['achievements'],
                  properties: {
                    achievements: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/Achievement' },
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/achievements/icons': {
      get: {
        tags: ['Achievements', 'Media & Presets'],
        summary: 'Публичный каталог 12 системных векторных SVG-иконок ачивок',
        description: 'Доступен также по алиасу `GET /api/v1/achievements/icons/presets`.',
        security: [],
        responses: {
          200: {
            description: 'Список всех 12 пресетных SVG-иконок',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['icons'],
                  properties: {
                    icons: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/AchievementIconPreset' },
                    },
                  },
                },
              },
            },
          },
        },
      },
    },
    '/achievements/icons/{slug}': {
      get: {
        tags: ['Achievements', 'Media & Presets'],
        summary: 'Отдача векторной SVG-иконки ачивки по slug',
        security: [],
        parameters: [
          {
            name: 'slug',
            in: 'path',
            required: true,
            schema: { type: 'string', example: 'sparkles.svg' },
          },
        ],
        responses: {
          200: {
            description: 'Векторная SVG-иконка (image/svg+xml)',
            content: { 'image/svg+xml': { schema: { type: 'string' } } },
          },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/achievements/{id}': {
      get: {
        tags: ['Achievements'],
        summary: 'Детальная карточка ачивки (по UUID или символьному коду) + последние 5 получивших студентов',
        parameters: [
          {
            name: 'id',
            in: 'path',
            required: true,
            schema: { type: 'string', example: 'WELCOME' },
            description: 'UUID или код ачивки (например, WELCOME, FIRST_BLOOD, SCORE_100)',
          },
        ],
        responses: {
          200: {
            description: 'Детали ачивки и список recentAchievers',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['achievement'],
                  properties: {
                    achievement: { $ref: '#/components/schemas/AchievementDetail' },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // LEADERBOARD
    // ──────────────────────────────────────────────────────────────────────────
    '/leaderboard': {
      get: {
        tags: ['Leaderboard'],
        summary: 'Рейтинг студентов за месяц (плоский отсортированный массив)',
        parameters: [
          { name: 'month', in: 'query', required: false, schema: { type: 'integer', example: 1 } },
          { name: 'groupNumber', in: 'query', required: false, schema: { type: 'string', example: '15' } },
        ],
        responses: {
          200: {
            description: 'Плоский массив студентов с их рангом, баллами и числом принятых ДЗ',
            content: {
              'application/json': {
                schema: {
                  type: 'array',
                  items: { $ref: '#/components/schemas/LeaderboardStudent' },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/leaderboard/top': {
      get: {
        tags: ['Leaderboard'],
        summary: 'Топ-5 студентов по баллам и топ-5 по числу принятых заданий',
        parameters: [
          { name: 'month', in: 'query', required: false, schema: { type: 'integer', example: 1 } },
          { name: 'groupNumber', in: 'query', required: false, schema: { type: 'string', example: '15' } },
        ],
        responses: {
          200: {
            description: 'Списки topByScore и topByTasks',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['month', 'topByScore', 'topByTasks'],
                  properties: {
                    month: { type: 'integer', example: 1 },
                    topByScore: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/LeaderboardStudent' },
                    },
                    topByTasks: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/LeaderboardStudent' },
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },
    '/leaderboard/archive/{month}': {
      get: {
        tags: ['Leaderboard'],
        summary: 'Исторический архив рейтинга за завершенный месяц',
        parameters: [{ name: 'month', in: 'path', required: true, schema: { type: 'integer', example: 1 } }],
        responses: {
          200: {
            description: 'Архивные записи рейтинга за выбранный месяц',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['month', 'recordsCount', 'archive'],
                  properties: {
                    month: { type: 'integer', example: 1 },
                    recordsCount: { type: 'integer', example: 25 },
                    archive: {
                      type: 'array',
                      items: {
                        type: 'object',
                        properties: {
                          id: { type: 'string', format: 'uuid' },
                          userId: { type: 'string', format: 'uuid' },
                          month: { type: 'integer', example: 1 },
                          finalScore: { type: 'integer', example: 180 },
                          tasksAcceptedCount: { type: 'integer', example: 8 },
                          finalRank: { type: 'integer', example: 1 },
                          archivedAt: { type: 'string', format: 'date-time' },
                          user: { $ref: '#/components/schemas/User' },
                        },
                      },
                    },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          401: { $ref: '#/components/responses/UnauthorizedError' },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // ADMIN: USERS & SCORES
    // ──────────────────────────────────────────────────────────────────────────
    '/admin/users': {
      get: {
        tags: ['Admin - Users & Scores'],
        summary: 'Список всех пользователей с фильтрацией по группе, месяцу и роли (Admin only)',
        parameters: [
          { name: 'groupNumber', in: 'query', schema: { type: 'string', example: '15' } },
          { name: 'month', in: 'query', schema: { type: 'integer', example: 1 } },
          { name: 'role', in: 'query', schema: { type: 'string', enum: ['STUDENT', 'ADMIN'] } },
        ],
        responses: {
          200: {
            description: 'Массив пользователей',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['users'],
                  properties: {
                    users: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/User' },
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
          403: { $ref: '#/components/responses/ForbiddenError' },
        },
      },
      post: {
        tags: ['Admin - Users & Scores'],
        summary: 'Создание нового студента или администратора/ментора (Admin only)',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['login', 'password'],
                properties: {
                  login: { type: 'string', minLength: 3, example: 'new_student' },
                  password: { type: 'string', minLength: 4, example: 'Pass1234' },
                  role: { type: 'string', enum: ['STUDENT', 'ADMIN'], default: 'STUDENT' },
                  name: { type: 'string', example: 'Иван Петров' },
                  groupNumber: { type: 'string', example: '15' },
                  groupId: { type: 'string', example: '15' },
                  currentMonth: { type: 'integer', default: 1 },
                  telegram: { type: 'string', example: '@ivan_petrov' },
                  telegramChatId: { type: 'string', example: '123456789' },
                  mentorId: { type: 'string', format: 'uuid', nullable: true },
                },
              },
            },
          },
        },
        responses: {
          201: {
            description: 'Пользователь успешно создан',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['user'],
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          403: { $ref: '#/components/responses/ForbiddenError' },
          409: { $ref: '#/components/responses/ConflictError' },
        },
      },
    },
    '/admin/users/bulk': {
      post: {
        tags: ['Admin - Users & Scores'],
        summary: 'Массовое создание аккаунтов студентов (Admin only)',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['users'],
                properties: {
                  users: {
                    type: 'array',
                    items: {
                      type: 'object',
                      required: ['login', 'password'],
                      properties: {
                        login: { type: 'string', example: 'student_10' },
                        password: { type: 'string', example: 'Pass1234' },
                        groupNumber: { type: 'string', example: '15' },
                        currentMonth: { type: 'integer', default: 1 },
                      },
                    },
                  },
                },
              },
            },
          },
        },
        responses: {
          201: {
            description: 'Студенты созданы',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    message: { type: 'string', example: 'Successfully created 10 students' },
                    count: { type: 'integer', example: 10 },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          409: { $ref: '#/components/responses/ConflictError' },
        },
      },
    },
    '/admin/users/{id}': {
      patch: {
        tags: ['Admin - Users & Scores'],
        summary: 'Редактирование данных пользователя, перевод между группами/месяцами, назначение ментора (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                properties: {
                  name: { type: 'string', nullable: true },
                  groupNumber: { type: 'string', nullable: true },
                  groupId: { type: 'string', nullable: true },
                  currentMonth: { type: 'integer' },
                  role: { type: 'string', enum: ['STUDENT', 'ADMIN'] },
                  password: { type: 'string', minLength: 4 },
                  telegram: { type: 'string', nullable: true },
                  telegramChatId: { type: 'string', nullable: true },
                  mentorId: { type: 'string', format: 'uuid', nullable: true },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Пользователь обновлен',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['user'],
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
      delete: {
        tags: ['Admin - Users & Scores'],
        summary: 'Удаление аккаунта пользователя (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        responses: {
          200: {
            description: 'Пользователь удален',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    message: { type: 'string', example: 'User deleted successfully' },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/admin/users/{id}/score-adjust': {
      post: {
        tags: ['Admin - Users & Scores'],
        summary: 'Начисление бонусных или штрафных баллов студенту с автоматической проверкой ачивок (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['amount', 'reason'],
                properties: {
                  amount: {
                    type: 'integer',
                    example: 20,
                    description: 'Положительное число для бонуса, отрицательное для штрафа',
                  },
                  reason: { type: 'string', example: 'Победа в хакатоне группы' },
                  month: { type: 'integer', example: 1 },
                },
              },
            },
          },
        },
        responses: {
          201: {
            description: 'Корректировка начислена и правила ачивок проверены',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['adjustment', 'awardedAchievements'],
                  properties: {
                    adjustment: { $ref: '#/components/schemas/ScoreAdjustment' },
                    awardedAchievements: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/Achievement' },
                    },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/admin/users/{id}/score-history': {
      get: {
        tags: ['Admin - Users & Scores'],
        summary: 'История всех бонусов и штрафов студента (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        responses: {
          200: {
            description: 'Суммарная корректировка и список всех записей ScoreAdjustment',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['userId', 'totalAdjustment', 'adjustments'],
                  properties: {
                    userId: { type: 'string', format: 'uuid' },
                    totalAdjustment: { type: 'integer', example: 35 },
                    adjustments: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/ScoreAdjustment' },
                    },
                  },
                },
              },
            },
          },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/admin/users/{id}/achievements': {
      post: {
        tags: ['Admin - Users & Scores', 'Achievements'],
        summary: 'Ручная выдача ачивки студенту по achievementCode или achievementId (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                properties: {
                  achievementCode: { type: 'string', example: 'SCORE_100' },
                  achievementId: { type: 'string', format: 'uuid' },
                },
              },
            },
          },
        },
        responses: {
          201: {
            description: 'Ачивка выдана студенту',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    userAchievement: { type: 'object' },
                  },
                },
              },
            },
          },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // ADMIN: LESSONS & TASKS
    // ──────────────────────────────────────────────────────────────────────────
    '/admin/lessons': {
      get: {
        tags: ['Admin - Lessons & Tasks'],
        summary: 'Список всех видеоуроков и доступных учебных групп (Admin only)',
        parameters: [
          { name: 'month', in: 'query', schema: { type: 'integer' } },
          { name: 'groupNumber', in: 'query', schema: { type: 'string' } },
        ],
        responses: {
          200: {
            description: 'Список уроков и массив availableGroups',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['lessons', 'availableGroups'],
                  properties: {
                    lessons: { type: 'array', items: { $ref: '#/components/schemas/Lesson' } },
                    availableGroups: { type: 'array', items: { type: 'string' } },
                  },
                },
              },
            },
          },
        },
      },
      post: {
        tags: ['Admin - Lessons & Tasks'],
        summary: 'Создание нового видеоурока (Admin only)',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['title', 'videoLink', 'groupNumber', 'month'],
                properties: {
                  title: { type: 'string', example: 'Урок 2: Кастомные хуки' },
                  videoLink: { type: 'string', example: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' },
                  groupNumber: { type: 'string', example: '15' },
                  month: { type: 'integer', example: 1 },
                  order: { type: 'integer', default: 1 },
                },
              },
            },
          },
        },
        responses: {
          201: {
            description: 'Урок создан',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: { lesson: { $ref: '#/components/schemas/Lesson' } },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
        },
      },
    },
    '/admin/lessons/{id}': {
      patch: {
        tags: ['Admin - Lessons & Tasks'],
        summary: 'Обновление видеоурока (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                properties: {
                  title: { type: 'string' },
                  videoLink: { type: 'string' },
                  groupNumber: { type: 'string' },
                  month: { type: 'integer' },
                  order: { type: 'integer' },
                },
              },
            },
          },
        },
        responses: {
          200: { description: 'Урок обновлен' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
      delete: {
        tags: ['Admin - Lessons & Tasks'],
        summary: 'Удаление видеоурока (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        responses: {
          200: { description: 'Урок удален' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/admin/tasks': {
      get: {
        tags: ['Admin - Lessons & Tasks'],
        summary: 'Список всех заданий с числом сдач (Admin only)',
        parameters: [{ name: 'month', in: 'query', schema: { type: 'integer' } }],
        responses: {
          200: {
            description: 'Массив заданий',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    tasks: { type: 'array', items: { $ref: '#/components/schemas/Task' } },
                  },
                },
              },
            },
          },
        },
      },
      post: {
        tags: ['Admin - Lessons & Tasks'],
        summary: 'Создание нового домашнего задания (Admin only)',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['title', 'description', 'topic', 'month'],
                properties: {
                  title: { type: 'string' },
                  description: { type: 'string' },
                  topic: { type: 'string' },
                  month: { type: 'integer', example: 1 },
                  order: { type: 'integer', default: 1 },
                  exampleLink: { type: 'string', nullable: true },
                  attachmentLink: { type: 'string', nullable: true },
                  hasScore: { type: 'boolean', default: true },
                  maxScore: { type: 'integer', nullable: true, default: 10 },
                  isBonus: { type: 'boolean', default: false },
                },
              },
            },
          },
        },
        responses: {
          201: { description: 'Задание создано' },
          400: { $ref: '#/components/responses/BadRequestError' },
        },
      },
    },
    '/admin/tasks/{id}': {
      patch: {
        tags: ['Admin - Lessons & Tasks'],
        summary: 'Редактирование домашнего задания (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                properties: {
                  title: { type: 'string' },
                  description: { type: 'string' },
                  topic: { type: 'string' },
                  month: { type: 'integer' },
                  order: { type: 'integer' },
                  exampleLink: { type: 'string', nullable: true },
                  attachmentLink: { type: 'string', nullable: true },
                  hasScore: { type: 'boolean' },
                  maxScore: { type: 'integer', nullable: true },
                  isBonus: { type: 'boolean' },
                },
              },
            },
          },
        },
        responses: {
          200: { description: 'Задание обновлено' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
      delete: {
        tags: ['Admin - Lessons & Tasks'],
        summary: 'Удаление домашнего задания (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        responses: {
          200: { description: 'Задание удалено' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // ADMIN: SUBMISSIONS & LEADERBOARD
    // ──────────────────────────────────────────────────────────────────────────
    '/admin/submissions': {
      get: {
        tags: ['Admin - Submissions & Leaderboard'],
        summary: 'Очередь работ на проверку ментором (Admin only)',
        parameters: [
          { name: 'status', in: 'query', schema: { type: 'string', enum: ['SENT', 'IN_REVIEW', 'REVISION', 'ACCEPTED'] } },
          { name: 'groupNumber', in: 'query', schema: { type: 'string' } },
          { name: 'month', in: 'query', schema: { type: 'integer' } },
        ],
        responses: {
          200: {
            description: 'Список сдач с данными студента, задания и проверяющего',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['submissions'],
                  properties: {
                    submissions: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/Submission' },
                    },
                  },
                },
              },
            },
          },
          401: { $ref: '#/components/responses/UnauthorizedError' },
          403: { $ref: '#/components/responses/ForbiddenError' },
        },
      },
    },
    '/admin/submissions/{id}': {
      get: {
        tags: ['Admin - Submissions & Leaderboard'],
        summary: 'Детальный просмотр сдачи ДЗ со всей историей попыток студента (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        responses: {
          200: {
            description: 'Объект submission и массив history всех версий по данному заданию',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['submission', 'history'],
                  properties: {
                    submission: { $ref: '#/components/schemas/Submission' },
                    history: {
                      type: 'array',
                      items: { $ref: '#/components/schemas/Submission' },
                    },
                  },
                },
              },
            },
          },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/admin/submissions/{id}/review': {
      patch: {
        tags: ['Admin - Submissions & Leaderboard'],
        summary: 'Вынесение вердикта и оценки ментором с авто-проверкой правил ачивок и уведомлением в Telegram (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['status'],
                properties: {
                  status: { type: 'string', enum: ['ACCEPTED', 'REVISION', 'IN_REVIEW'] },
                  score: { type: 'integer', nullable: true, example: 10 },
                  reviewerComment: { type: 'string', nullable: true, example: 'Чистая архитектура, принято!' },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Решение проверено, возвращает обновленную сдачу и список новых выданных ачивок',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['submission', 'awardedAchievements'],
                  properties: {
                    submission: { $ref: '#/components/schemas/Submission' },
                    awardedAchievements: {
                      type: 'array',
                      items: { type: 'string', example: 'FIRST_BLOOD' },
                    },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
          404: { $ref: '#/components/responses/NotFoundError' },
        },
      },
    },
    '/admin/leaderboard/archive-and-reset': {
      post: {
        tags: ['Admin - Submissions & Leaderboard', 'Leaderboard'],
        summary: 'Архивация рейтинга за месяц и опциональный перевод студентов на следующий месяц (Admin only)',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['month'],
                properties: {
                  month: { type: 'integer', example: 1 },
                  incrementMonth: { type: 'boolean', default: false },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: 'Месяц успешно заархивирован',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    message: { type: 'string', example: 'Month 1 successfully archived' },
                    month: { type: 'integer', example: 1 },
                    archivedCount: { type: 'integer', example: 25 },
                    studentsIncrementedCount: { type: 'integer', example: 25 },
                  },
                },
              },
            },
          },
          400: { $ref: '#/components/responses/BadRequestError' },
        },
      },
    },

    // ──────────────────────────────────────────────────────────────────────────
    // HEALTH
    // ──────────────────────────────────────────────────────────────────────────
    '/health': {
      get: {
        tags: ['Health'],
        summary: 'Проверка состояния сервера, БД Neon PostgreSQL и Telegram-бота',
        security: [],
        parameters: [
          {
            name: 'shallow',
            in: 'query',
            required: false,
            schema: { type: 'boolean', example: false },
            description: 'Если `true`, пропускает SQL-пинг базы данных для мгновенного ответа',
          },
        ],
        responses: {
          200: {
            description: 'Сервис полностью исправен',
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/HealthCheckResponse' },
              },
            },
          },
          503: {
            description: 'Деградация сервиса (например, недоступна БД)',
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/HealthCheckResponse' },
              },
            },
          },
        },
      },
    },
  },
};

export function setupSwagger(app: Express): void {
  app.use('/api/docs', swaggerUi.serve, swaggerUi.setup(swaggerDocument));
  app.get('/api/docs-json', (req: Request, res: Response) => {
    const origin = getPublicOrigin(req);
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.json({
      ...swaggerDocument,
      servers: [
        {
          url: `${origin}/api/v1`,
          description: 'Current API v1 Server',
        },
        {
          url: '/api/v1',
          description: 'Relative API v1 Root',
        },
      ],
    });
  });
}
