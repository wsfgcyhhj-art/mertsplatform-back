import { Express } from 'express';
import swaggerUi from 'swagger-ui-express';

export const swaggerDocument = {
  openapi: '3.0.0',
  info: {
    title: 'Merts Platform v2 API',
    version: '2.0.0',
    description: 'API backend платформы обучения Merts Platform: аутентификация, регистрация, уроки, задания, сдачи решений, геймификация и лидерборд.',
  },
  servers: [
    {
      url: '/api/v1',
      description: 'API v1 root',
    },
  ],
  components: {
    securitySchemes: {
      bearerAuth: {
        type: 'http',
        scheme: 'bearer',
        bearerFormat: 'JWT',
      },
    },
    schemas: {
      ErrorResponse: {
        type: 'object',
        properties: {
          statusCode: { type: 'integer', example: 404 },
          error: { type: 'string', example: 'Not Found' },
          message: { type: 'string', example: 'Task not found' },
        },
      },
      User: {
        type: 'object',
        properties: {
          id: { type: 'string', format: 'uuid' },
          login: { type: 'string' },
          role: { type: 'string', enum: ['STUDENT', 'ADMIN'] },
          name: { type: 'string', nullable: true },
          telegram: { type: 'string', nullable: true },
          groupNumber: { type: 'string', nullable: true },
          groupId: { type: 'string', nullable: true },
          currentMonth: { type: 'integer' },
          avatarUrl: { type: 'string', nullable: true },
          bannerUrl: { type: 'string', nullable: true },
        },
      },
      LeaderboardStudent: {
        type: 'object',
        properties: {
          rank: { type: 'integer', example: 1 },
          id: { type: 'string', format: 'uuid' },
          name: { type: 'string', nullable: true },
          login: { type: 'string' },
          avatarUrl: { type: 'string', nullable: true },
          groupNumber: { type: 'string', nullable: true },
          currentMonth: { type: 'integer' },
          totalScore: { type: 'integer', example: 150 },
          tasksSentCount: { type: 'integer', example: 5 },
          tasksAcceptedCount: { type: 'integer', example: 4 },
        },
      },
      Lesson: {
        type: 'object',
        properties: {
          id: { type: 'string', format: 'uuid' },
          title: { type: 'string' },
          videoLink: { type: 'string' },
          youtubeId: { type: 'string' },
          month: { type: 'integer' },
          order: { type: 'integer' },
        },
      },
      Task: {
        type: 'object',
        properties: {
          id: { type: 'string', format: 'uuid' },
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
      Submission: {
        type: 'object',
        properties: {
          id: { type: 'string', format: 'uuid' },
          taskId: { type: 'string', format: 'uuid' },
          userId: { type: 'string', format: 'uuid' },
          version: { type: 'integer' },
          solutionLink: { type: 'string' },
          comment: { type: 'string', nullable: true },
          status: { type: 'string', enum: ['SENT', 'IN_REVIEW', 'REVISION', 'ACCEPTED'] },
          score: { type: 'integer', nullable: true },
          reviewerComment: { type: 'string', nullable: true },
          reviewedAt: { type: 'string', format: 'date-time', nullable: true },
          createdAt: { type: 'string', format: 'date-time' },
        },
      },
      Achievement: {
        type: 'object',
        properties: {
          id: { type: 'string', format: 'uuid' },
          code: { type: 'string' },
          title: { type: 'string' },
          description: { type: 'string' },
          iconUrl: { type: 'string' },
          category: { type: 'string' },
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
          },
          threshold: { type: 'integer', nullable: true },
          isActive: { type: 'boolean' },
          criteria: { type: 'string' },
          points: { type: 'integer' },
          unlockedCount: { type: 'integer' },
          isUnlockedByMe: { type: 'boolean' },
          unlockedAt: { type: 'string', format: 'date-time', nullable: true },
        },
      },
    },
  },
  security: [{ bearerAuth: [] }],
  paths: {
    '/auth/register': {
      post: {
        summary: 'Регистрация нового студента',
        security: [],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['login', 'password', 'groupNumber'],
                properties: {
                  login: { type: 'string', minLength: 3 },
                  password: { type: 'string', minLength: 8 },
                  groupNumber: { type: 'string' },
                  name: { type: 'string' },
                  telegram: { type: 'string' },
                  groupId: { type: 'string' },
                  currentMonth: { type: 'integer', default: 1 },
                },
              },
            },
          },
        },
        responses: {
          201: { description: 'Студент зарегистрирован, возвращает accessToken и ставит cookie refreshToken' },
          400: { description: 'Не заполнены обязательные поля' },
          409: { description: 'Пользователь с таким логином уже существует' },
        },
      },
    },
    '/auth/login': {
      post: {
        summary: 'Вход в систему',
        security: [],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['login', 'password'],
                properties: {
                  login: { type: 'string', minLength: 3 },
                  password: { type: 'string', minLength: 8 },
                },
              },
            },
          },
        },
        responses: {
          200: { description: 'Успешный вход, возвращает accessToken и ставит HttpOnly cookie refreshToken' },
          401: { description: 'Неверные учетные данные' },
        },
      },
    },
    '/auth/refresh': {
      post: {
        summary: 'Ротация токенов по refreshToken cookie',
        security: [],
        responses: {
          200: { description: 'Новый accessToken' },
          401: { description: 'Невалидный или истекший refresh токен' },
        },
      },
    },
    '/auth/logout': {
      post: {
        summary: 'Выход и удаление сессии',
        responses: {
          200: { description: 'Успешный выход' },
        },
      },
    },
    '/me': {
      get: {
        summary: 'Профиль текущего пользователя со статистикой',
        responses: {
          200: { description: 'Данные профиля и счетчики баллов/задач' },
        },
      },
    },
    '/users/me/avatar': {
      post: {
        summary: 'Загрузка файла аватарки студента (multipart/form-data)',
        description:
          'Принимает файл изображения (JPEG, PNG, WebP, GIF, SVG до 2 МБ), автоматически оптимизирует в 256×256 WebP (quality 85), сохраняет в таблицу MediaAsset БД Neon и обновляет user.avatarUrl.',
        tags: ['Users', 'Media'],
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
            description: 'Аватар успешно загружен, оптимизирован и сохранен на бэкенде',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                    avatarUrl: { type: 'string', example: '/api/v1/media/3fa85f64-5717-4562-b3fc-2c963f66afa6' },
                    assetId: { type: 'string', format: 'uuid' },
                  },
                },
              },
            },
          },
          400: { description: 'Отсутствует файл или недопустимый формат/размер (> 2 МБ)' },
          401: { description: 'Пользователь не авторизован' },
        },
      },
      patch: {
        summary: 'Обновление аватарки по URL пресета или сброс',
        description: 'Обновляет URL (например, пресет /api/v1/media/presets/avatars/amber-coder.svg) или сбрасывает аватарку (null).',
        tags: ['Users'],
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
                    example: '/api/v1/media/presets/avatars/amber-coder.svg',
                    description: 'Ссылка на пресет с бэкенда, внешний URL или null для сброса',
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
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                  },
                },
              },
            },
          },
          400: {
            description: 'Некорректные входные данные',
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/ErrorResponse' },
                example: {
                  statusCode: 400,
                  error: 'Bad Request',
                  message: 'avatarUrl must be a string or null',
                },
              },
            },
          },
          401: {
            description: 'Пользователь не авторизован',
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/ErrorResponse' },
                example: {
                  statusCode: 401,
                  error: 'Unauthorized',
                  message: 'Unauthorized',
                },
              },
            },
          },
        },
      },
    },
    '/users/me/banner': {
      post: {
        summary: 'Загрузка файла обоев/баннера профиля (multipart/form-data)',
        description:
          'Принимает файл обложки профиля (JPEG, PNG, WebP, GIF, SVG до 5 МБ), автоматически оптимизирует в 1600×400 WebP (quality 85), сохраняет в таблицу MediaAsset БД Neon и обновляет user.bannerUrl.',
        tags: ['Users', 'Media'],
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
            description: 'Баннер успешно загружен, оптимизирован и сохранен на бэкенде',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                    bannerUrl: { type: 'string', example: '/api/v1/media/7b29c4a1-9123-4bc1-8890-12a4567890ef' },
                    assetId: { type: 'string', format: 'uuid' },
                  },
                },
              },
            },
          },
          400: { description: 'Отсутствует файл или недопустимый формат/размер (> 5 МБ)' },
          401: { description: 'Пользователь не авторизован' },
        },
      },
      patch: {
        summary: 'Обновление баннера профиля по URL пресета или сброс',
        description: 'Обновляет шапку профиля по URL пресета (например, /api/v1/media/presets/banners/linear-graphite.svg) или сбрасывает в null.',
        tags: ['Users'],
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
                    description: 'Ссылка на пресет баннера с бэкенда, внешний URL или null для сброса',
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
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                  },
                },
              },
            },
          },
          400: {
            description: 'Некорректные входные данные',
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/ErrorResponse' },
                example: {
                  statusCode: 400,
                  error: 'Bad Request',
                  message: 'bannerUrl must be a string or null',
                },
              },
            },
          },
          401: {
            description: 'Пользователь не авторизован',
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/ErrorResponse' },
                example: {
                  statusCode: 401,
                  error: 'Unauthorized',
                  message: 'Unauthorized',
                },
              },
            },
          },
        },
      },
    },
    '/media/presets': {
      get: {
        summary: 'Каталог готовых обоев профиля, дефолтных аватаров и пресетов иконок ачивок',
        tags: ['Media'],
        security: [],
        responses: {
          200: {
            description: 'Возвращает списки banners, avatars и achievementIcons с URL и Data URI',
          },
        },
      },
    },
    '/media/{id}': {
      get: {
        summary: 'Отдача загруженного медиафайла (аватар, баннер, иконка) из БД Neon',
        tags: ['Media'],
        security: [],
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: {
          200: { description: 'Бинарный поток изображения (image/webp, image/svg+xml) с иммутабельным кэшированием' },
          404: { description: 'Медиафайл не найден' },
        },
      },
    },
    '/users/me/profile': {
      patch: {
        summary: 'Частичное обновление профиля пользователя',
        description: 'Обновляет отображаемое имя (name) и/или Telegram-юзернейм (telegram). Изменение группы студентом строго запрещено.',
        tags: ['Users'],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                properties: {
                  name: {
                    type: 'string',
                    nullable: true,
                    example: 'Алексей Иванов',
                    description: 'Имя и фамилия студента',
                  },
                  telegram: {
                    type: 'string',
                    nullable: true,
                    example: '@alex_ivanov',
                    description: 'Telegram username (с @ или без, от 5 до 32 символов) или null для сброса',
                  },
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
                  properties: {
                    user: { $ref: '#/components/schemas/User' },
                  },
                },
              },
            },
          },
          400: {
            description: 'Ошибка валидации или попытка изменить группу студентом',
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/ErrorResponse' },
                examples: {
                  groupForbidden: {
                    summary: 'Попытка сменить группу',
                    value: {
                      statusCode: 400,
                      error: 'Bad Request',
                      message: 'Изменение группы студентом запрещено',
                    },
                  },
                  invalidTelegram: {
                    summary: 'Некорректный Telegram username',
                    value: {
                      statusCode: 400,
                      error: 'Bad Request',
                      message: 'Некорректный формат Telegram username (от 5 до 32 символов: @username)',
                    },
                  },
                },
              },
            },
          },
          401: {
            description: 'Пользователь не авторизован',
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/ErrorResponse' },
                example: {
                  statusCode: 401,
                  error: 'Unauthorized',
                  message: 'Unauthorized',
                },
              },
            },
          },
        },
      },
    },
    '/me/achievements': {
      get: {
        summary: 'Ачивки текущего студента',
        responses: {
          200: { description: 'Список полученных ачивок' },
        },
      },
    },
    '/lessons': {
      get: {
        summary: 'Уроки строго текущего месяца студента',
        responses: {
          200: { description: 'Список уроков текущего месяца' },
        },
      },
    },
    '/tasks': {
      get: {
        summary: 'Задания текущего месяца студента с latestSubmission',
        responses: {
          200: { description: 'Список заданий с результатами сдачи' },
        },
      },
    },
    '/tasks/{id}': {
      get: {
        summary: 'Детальная карточка задания с историей сдач',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: {
          200: { description: 'Задание и массив всех попыток сдачи' },
          404: { description: 'Задание не найдено или принадлежит другому месяцу' },
        },
      },
    },
    '/tasks/{id}/submissions': {
      post: {
        summary: 'Отправка решения студентом (повторная сдача только при статусе REVISION)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['solutionLink'],
                properties: {
                  solutionLink: { type: 'string', example: 'https://github.com/student/homework-1' },
                  comment: { type: 'string' },
                },
              },
            },
          },
        },
        responses: {
          201: { description: 'Решение отправлено' },
          400: { description: 'Невалидный URL github.com или предыдущая сдача еще на проверке/принята' },
        },
      },
    },
    '/leaderboard': {
      get: {
        summary: 'Рейтинг и лидерборд студентов за месяц (плоский массив)',
        parameters: [
          { name: 'month', in: 'query', schema: { type: 'integer' } },
          { name: 'groupNumber', in: 'query', schema: { type: 'string' } },
        ],
        responses: {
          200: {
            description: 'Плоский массив студентов',
            content: {
              'application/json': {
                schema: {
                  type: 'array',
                  items: { $ref: '#/components/schemas/LeaderboardStudent' },
                },
              },
            },
          },
        },
      },
    },
    '/leaderboard/top': {
      get: {
        summary: 'Топ-5 студентов по баллам и топ-5 по задачам',
        responses: {
          200: { description: 'Топ-5 списки' },
        },
      },
    },
    '/leaderboard/archive/{month}': {
      get: {
        summary: 'Просмотр архива месяца',
        parameters: [{ name: 'month', in: 'path', required: true, schema: { type: 'integer' } }],
        responses: {
          200: { description: 'Архивные данные месяца' },
        },
      },
    },
    '/achievements': {
      get: {
        summary: 'Каталог всех ачивок платформы',
        responses: {
          200: { description: 'Список ачивок с метаданными и статусом разблокировки' },
        },
      },
    },
    '/achievements/{id}': {
      get: {
        summary: 'Детальная информация об ачивке (по id или code) с топ-5 получившими',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: {
          200: { description: 'Детали ачивки, критерии, баллы и последние получившие студенты' },
          404: { description: 'Ачивка не найдена' },
        },
      },
    },
    '/admin/submissions': {
      get: {
        summary: 'Очередь работ на проверку ментором (Admin only)',
        parameters: [
          { name: 'status', in: 'query', schema: { type: 'string', enum: ['SENT', 'IN_REVIEW', 'REVISION', 'ACCEPTED'] } },
          { name: 'groupNumber', in: 'query', schema: { type: 'string' } },
          { name: 'month', in: 'query', schema: { type: 'integer' } },
        ],
        responses: {
          200: { description: 'Очередь решений' },
        },
      },
    },
    '/admin/submissions/{id}/review': {
      patch: {
        summary: 'Проверка и оценка решения ментором (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['status'],
                properties: {
                  status: { type: 'string', enum: ['ACCEPTED', 'REVISION', 'IN_REVIEW'] },
                  score: { type: 'integer' },
                  reviewerComment: { type: 'string' },
                },
              },
            },
          },
        },
        responses: {
          200: { description: 'Решение проверено, возвращает обновленную сдачу и выданные ачивки' },
        },
      },
    },
    '/admin/users/{id}/score-adjust': {
      post: {
        summary: 'Начисление бонусов/штрафов ментором (Admin only)',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['amount', 'reason'],
                properties: {
                  amount: { type: 'integer', description: 'Положительное число для бонуса, отрицательное для штрафа' },
                  reason: { type: 'string' },
                  month: { type: 'integer' },
                },
              },
            },
          },
        },
        responses: {
          201: { description: 'Корректировка создана' },
        },
      },
    },
    '/admin/leaderboard/archive-and-reset': {
      post: {
        summary: 'Архивация месяца и сброс/инкремент (Admin only)',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['month'],
                properties: {
                  month: { type: 'integer' },
                  incrementMonth: { type: 'boolean' },
                },
              },
            },
          },
        },
        responses: {
          200: { description: 'Месяц заархивирован' },
        },
      },
    },
  },
};

export function setupSwagger(app: Express): void {
  app.use('/api/docs', swaggerUi.serve, swaggerUi.setup(swaggerDocument));
  app.get('/api/docs-json', (_req, res) => {
    res.json(swaggerDocument);
  });
}
