import crypto from 'node:crypto';
import { EventEmitter } from 'node:events';
import { Role } from '@prisma/client';
import { prisma } from '../prisma.js';
import { config } from '../config.js';
import { evaluateUserAchievements } from './achievementService.js';
import { sendTelegramNotification, escapeTelegramHtml } from './telegramService.js';

export interface PlatformEventMap {
  USER_REGISTERED: {
    userId: string;
    login: string;
    groupNumber: string | null;
  };
  USER_LOGIN: {
    userId: string;
    login: string;
    streakCount: number;
  };
  SUBMISSION_CREATED: {
    submissionId: string;
    userId: string;
    taskId: string;
    version: number;
    streakCount: number;
  };
  SUBMISSION_REVIEWED: {
    submissionId: string;
    userId: string;
    taskId: string;
    status: string;
    score: number | null;
    reviewerComment: string | null;
  };
  SCORE_ADJUSTED: {
    adjustmentId: string;
    userId: string;
    adminId: string;
    amount: number;
    reason: string;
    month: number;
  };
  ACHIEVEMENT_UNLOCKED: {
    userId: string;
    achievementCode: string;
    title: string;
    points: number;
  };
  EASTER_EGG_CLAIMED: {
    userId: string;
    achievementCode: string | null;
  };
  TELEGRAM_LINKED: {
    userId: string;
    telegramChatId: string;
    telegramUsername: string | null;
  };
  LESSON_CREATED: {
    lessonId: string;
    title: string;
    groupNumber: string;
    month: number;
  };
  TASK_CREATED: {
    taskId: string;
    title: string;
    topic: string;
    month: number;
    isBonus: boolean;
  };
}

export type PlatformEventName = keyof PlatformEventMap;

class PlatformEventBus {
  private emitter = new EventEmitter();

  constructor() {
    this.emitter.setMaxListeners(30);
    this.registerCoreSubscribers();
  }

  public on<K extends PlatformEventName>(
    eventName: K,
    listener: (payload: PlatformEventMap[K]) => void | Promise<void>
  ): void {
    this.emitter.on(eventName, async (payload: PlatformEventMap[K]) => {
      try {
        await listener(payload);
      } catch (err) {
        console.error(`[EventBus] Error in listener for ${eventName}:`, (err as Error)?.message || err);
      }
    });
  }

  public emit<K extends PlatformEventName>(eventName: K, payload: PlatformEventMap[K]): void {
    this.emitter.emit(eventName, payload);
    this.dispatchOutboundWebhook(eventName, payload).catch((err) => {
      console.warn(`[EventBus] Outbound webhook failed for ${eventName}:`, (err as Error)?.message || err);
    });
  }

  private async dispatchOutboundWebhook<K extends PlatformEventName>(
    event: K,
    payload: PlatformEventMap[K]
  ): Promise<void> {
    const webhookUrl = (process.env.WEBHOOK_URL || '').trim();
    if (!webhookUrl) return;

    const bodyStr = JSON.stringify({
      event,
      timestamp: new Date().toISOString(),
      payload,
    });

    const secret = (process.env.WEBHOOK_SECRET || config.jwt.accessSecret || 'merts-webhook').trim();
    const signature = crypto.createHmac('sha256', secret).update(bodyStr).digest('hex');

    await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Merts-Event': event,
        'X-Merts-Signature': `sha256=${signature}`,
      },
      body: bodyStr,
    });
  }

  private registerCoreSubscribers(): void {
    // 1. SCORE_ADJUSTED -> проверка правил ачивок + мгновенное уведомление студенту в Telegram
    this.on('SCORE_ADJUSTED', async (payload) => {
      await evaluateUserAchievements(payload.userId, { trigger: 'SCORE_ADJUSTED' });

      const sign = payload.amount >= 0 ? `+${payload.amount}` : `${payload.amount}`;
      const badge = payload.amount >= 0 ? '🎁 <b>Начислены бонусные баллы!</b>' : '⚠️ <b>Корректировка баллов</b>';
      const lines = [
        badge,
        `Изменение: <b>${sign} pts</b> (Месяц ${payload.month})`,
        `Причина: <i>${escapeTelegramHtml(payload.reason)}</i>`,
      ];
      await sendTelegramNotification(payload.userId, lines.join('\n'));
    });

    // 2. TASK_CREATED -> уведомление студентов соответствующего месяца в Telegram
    this.on('TASK_CREATED', async (payload) => {
      const students = await prisma.user.findMany({
        where: {
          role: Role.STUDENT,
          currentMonth: payload.month,
          telegramChatId: { not: null },
        },
        select: { id: true },
      });

      if (students.length === 0) return;

      const bonusBadge = payload.isBonus ? ' (⭐ Бонусное)' : '';
      const message = [
        `📌 <b>Опубликовано новое домашнее задание${bonusBadge}!</b>`,
        `Тема: <b>${escapeTelegramHtml(payload.topic)}</b>`,
        `Задание: <b>${escapeTelegramHtml(payload.title)}</b> (Месяц ${payload.month})`,
      ].join('\n');

      for (const st of students) {
        await sendTelegramNotification(st.id, message);
      }
    });

    // 3. LESSON_CREATED -> уведомление студентов группы и месяца о новом видеоуроке
    this.on('LESSON_CREATED', async (payload) => {
      const groupFilter =
        payload.groupNumber === 'ALL'
          ? {}
          : { groupNumber: payload.groupNumber };

      const students = await prisma.user.findMany({
        where: {
          role: Role.STUDENT,
          currentMonth: payload.month,
          telegramChatId: { not: null },
          ...groupFilter,
        },
        select: { id: true },
      });

      if (students.length === 0) return;

      const message = [
        '🎬 <b>Добавлен новый видеоурок!</b>',
        `Урок: <b>${escapeTelegramHtml(payload.title)}</b>`,
        `Группа: <b>${escapeTelegramHtml(payload.groupNumber)}</b> | Месяц <b>${payload.month}</b>`,
      ].join('\n');

      for (const st of students) {
        await sendTelegramNotification(st.id, message);
      }
    });
  }
}

export const eventBus = new PlatformEventBus();
