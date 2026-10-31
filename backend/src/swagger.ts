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
                required: ['login', 'password', 'name', 'telegram', 'groupNumber', 'groupId'],
                properties: {
                  login: { type: 'string' },
                  password: { type: 'string' },
                  name: { type: 'string' },
                  telegram: { type: 'string' },
                  groupNumber: { type: 'string' },
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
                  login: { type: 'string' },
                  password: { type: 'string' },
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
      patch: {
        summary: 'Полное редактирование профиля и смена пароля',
        requestBody: {
          content: {
            'application/json': {
              schema: {
                type: 'object',
                properties: {
                  name: { type: 'string' },
                  telegram: { type: 'string' },
                  avatarUrl: { type: 'string', nullable: true },
                  bannerUrl: { type: 'string', nullable: true },
                  currentPassword: { type: 'string' },
                  newPassword: { type: 'string' },
                },
              },
            },
          },
        },
        responses: {
          200: { description: 'Обновленный профиль' },
          400: { description: 'Неверный текущий пароль или ошибка валидации' },
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
