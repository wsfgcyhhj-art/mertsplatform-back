import cron from 'node-cron';
import { Role, SubmissionStatus } from '@prisma/client';
import { prisma } from '../prisma.js';
import { config } from '../config.js';
import {
  escapeTelegramHtml,
  sendTelegramMessageToChatId,
  sendTelegramNotification,
} from './telegramService.js';

export interface WeeklyLeaderItem {
  id: string;
  name: string;
  login: string;
  points: number;
}

/**
 * Находит Топ-3 студентов по количеству набранных баллов за последние 7 дней.
 * Если за последние 7 дней меньше 3 студентов с баллами, дополняет список по общему рейтингу.
 */
export async function getWeeklyTop3Students(): Promise<WeeklyLeaderItem[]> {
  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);

  const students = await prisma.user.findMany({
    where: { role: Role.STUDENT },
    select: {
      id: true,
      name: true,
      login: true,
    },
  });

  if (students.length === 0) {
    return [];
  }

  const studentIds = students.map((s) => s.id);

  const [recentSubmissions, recentAdjustments, allAcceptedSubmissions, allAdjustments] =
    await Promise.all([
      prisma.submission.findMany({
        where: {
          userId: { in: studentIds },
          status: SubmissionStatus.ACCEPTED,
          updatedAt: { gte: sevenDaysAgo },
        },
        select: {
          userId: true,
          score: true,
        },
      }),
      prisma.scoreAdjustment.findMany({
        where: {
          userId: { in: studentIds },
          createdAt: { gte: sevenDaysAgo },
        },
        select: {
          userId: true,
          amount: true,
        },
      }),
      prisma.submission.findMany({
        where: {
          userId: { in: studentIds },
          status: SubmissionStatus.ACCEPTED,
        },
        select: {
          userId: true,
          score: true,
        },
      }),
      prisma.scoreAdjustment.findMany({
        where: {
          userId: { in: studentIds },
        },
        select: {
          userId: true,
          amount: true,
        },
      }),
    ]);

  const weeklyScores = new Map<string, number>();
  for (const sub of recentSubmissions) {
    weeklyScores.set(sub.userId, (weeklyScores.get(sub.userId) || 0) + (sub.score || 0));
  }
  for (const adj of recentAdjustments) {
    weeklyScores.set(adj.userId, (weeklyScores.get(adj.userId) || 0) + adj.amount);
  }

  const totalScores = new Map<string, number>();
  for (const sub of allAcceptedSubmissions) {
    totalScores.set(sub.userId, (totalScores.get(sub.userId) || 0) + (sub.score || 0));
  }
  for (const adj of allAdjustments) {
    totalScores.set(adj.userId, (totalScores.get(adj.userId) || 0) + adj.amount);
  }

  const ranked = students
    .map((s) => {
      const weekly = weeklyScores.get(s.id) ?? 0;
      const total = totalScores.get(s.id) ?? 0;
      return {
        id: s.id,
        name: s.name || s.login,
        login: s.login,
        points: weekly > 0 ? weekly : total,
        weeklyPoints: weekly,
        totalPoints: total,
      };
    })
    .sort((a, b) => {
      if (b.weeklyPoints !== a.weeklyPoints) {
        return b.weeklyPoints - a.weeklyPoints;
      }
      return b.totalPoints - a.totalPoints;
    })
    .slice(0, 3);

  return ranked.map(({ id, name, login, points }) => ({
    id,
    name,
    login,
    points,
  }));
}

export async function buildWeeklyDigestMessage(): Promise<string> {
  const top3 = await getWeeklyTop3Students();

  const u1 = top3[0] ?? { name: '—', points: 0 };
  const u2 = top3[1] ?? { name: '—', points: 0 };
  const u3 = top3[2] ?? { name: '—', points: 0 };

  return [
    '🏆 <b>ИТОГИ НЕДЕЛИ MERTSPLATFORM</b> 🚀',
    '',
    'Поздравляем лидеров прошедшей недели:',
    `🥇 1 место — <b>${escapeTelegramHtml(u1.name)}</b> (+${u1.points} pts)`,
    `🥈 2 место — <b>${escapeTelegramHtml(u2.name)}</b> (+${u2.points} pts)`,
    `🥉 3 место — <b>${escapeTelegramHtml(u3.name)}</b> (+${u3.points} pts)`,
    '',
    '<i>Не сбавляем темп! Сдавайте домашние задания вовремя и держите свои стрики активными! 🔥</i>',
  ].join('\n');
}

export function getIsoWeekKey(d: Date = new Date()): string {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${date.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

let lastBroadcastWeekKey: string | null = null;

export function getLastBroadcastWeekKey(): string | null {
  return lastBroadcastWeekKey;
}

export function resetBroadcastWeekKeyForTesting(): void {
  lastBroadcastWeekKey = null;
}

export async function runWeeklyDigestBroadcast(options?: {
  force?: boolean;
}): Promise<{
  message: string;
  sentToCourseChat: boolean;
  sentToUsersCount: number;
  skippedDueToDuplicate?: boolean;
}> {
  const isForce = Boolean(options?.force);
  const currentWeekKey = getIsoWeekKey();

  if (!isForce && lastBroadcastWeekKey === currentWeekKey) {
    console.log(
      `[Cron Digest] Weekly digest for ${currentWeekKey} was already broadcast. Skipping duplicate run.`
    );
    return {
      message: '',
      sentToCourseChat: false,
      sentToUsersCount: 0,
      skippedDueToDuplicate: true,
    };
  }

  try {
    const message = await buildWeeklyDigestMessage();

    let sentToCourseChat = false;
    const courseChatId = (process.env.TELEGRAM_COURSE_CHAT_ID || config.telegram.courseChatId || '').trim();
    if (courseChatId && courseChatId !== 'your_channel_or_group_id') {
      sentToCourseChat = await sendTelegramMessageToChatId(courseChatId, message);
    }

    const connectedUsers = await prisma.user.findMany({
      where: {
        telegramChatId: { not: null },
      },
      select: {
        id: true,
      },
    });

    let sentToUsersCount = 0;
    for (const u of connectedUsers) {
      const ok = await sendTelegramNotification(u.id, message);
      if (ok) {
        sentToUsersCount += 1;
      }
    }

    lastBroadcastWeekKey = currentWeekKey;

    return {
      message,
      sentToCourseChat,
      sentToUsersCount,
      skippedDueToDuplicate: false,
    };
  } catch (err) {
    console.error('[Cron Digest] Failed to broadcast weekly digest:', err);
    return {
      message: '',
      sentToCourseChat: false,
      sentToUsersCount: 0,
    };
  }
}

/**
 * Автоматическая уборка БД:
 * 1) Удаляет истекшие JWT-сессии (expiresAt < now).
 * 2) Очищает неиспользованные одноразовые коды привязки Telegram старше 24 часов.
 */
export async function runMaintenanceCleanup(): Promise<{
  expiredSessionsDeleted: number;
  staleAuthCodesCleared: number;
}> {
  const now = new Date();
  const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);

  const [sessionResult, authCodeResult] = await Promise.all([
    prisma.session.deleteMany({
      where: { expiresAt: { lt: now } },
    }),
    prisma.user.updateMany({
      where: {
        telegramAuthCode: { not: null },
        telegramChatId: null,
        updatedAt: { lt: oneDayAgo },
      },
      data: {
        telegramAuthCode: null,
      },
    }),
  ]);

  return {
    expiredSessionsDeleted: sessionResult.count,
    staleAuthCodesCleared: authCodeResult.count,
  };
}

/**
 * Еженедельные пятничные напоминания студентам о несданных обязательных ДЗ текущего месяца.
 */
export async function runHomeworkRemindersBroadcast(): Promise<{
  notifiedStudentsCount: number;
}> {
  if (process.env.ENABLE_HOMEWORK_REMINDERS === 'false') {
    return { notifiedStudentsCount: 0 };
  }

  const students = await prisma.user.findMany({
    where: {
      role: Role.STUDENT,
      telegramChatId: { not: null },
    },
    select: {
      id: true,
      name: true,
      login: true,
      currentMonth: true,
    },
  });

  if (students.length === 0) {
    return { notifiedStudentsCount: 0 };
  }

  const allTasks = await prisma.task.findMany({
    where: { isBonus: false },
    select: { id: true, title: true, month: true },
  });

  const submissions = await prisma.submission.findMany({
    where: {
      userId: { in: students.map((s) => s.id) },
    },
    select: {
      userId: true,
      taskId: true,
      status: true,
    },
  });

  let notifiedStudentsCount = 0;

  for (const st of students) {
    const monthTasks = allTasks.filter((t) => t.month === st.currentMonth);
    if (monthTasks.length === 0) continue;

    const mySubTaskIds = new Set(
      submissions
        .filter((s) => s.userId === st.id && s.status !== SubmissionStatus.REVISION)
        .map((s) => s.taskId)
    );

    const pendingTasks = monthTasks.filter((t) => !mySubTaskIds.has(t.id));
    if (pendingTasks.length === 0) continue;

    const previewTitles = pendingTasks
      .slice(0, 3)
      .map((t) => `• ${escapeTelegramHtml(t.title)}`)
      .join('\n');

    const msg = [
      `⏰ <b>Напоминание о домашних заданиях (Месяц ${st.currentMonth})</b>`,
      `У вас осталось <b>${pendingTasks.length}</b> несданных обязательных ДЗ:`,
      previewTitles,
      '',
      '<i>Сдайте решения до конца недели, чтобы сохранить стрик и подняться в лидерборде! 🚀</i>',
    ].join('\n');

    const ok = await sendTelegramNotification(st.id, msg);
    if (ok) notifiedStudentsCount += 1;
  }

  return { notifiedStudentsCount };
}

let digestTask: ReturnType<typeof cron.schedule> | null = null;
let cleanupTask: ReturnType<typeof cron.schedule> | null = null;
let reminderTask: ReturnType<typeof cron.schedule> | null = null;

export function initWeeklyDigestCron(): void {
  stopWeeklyDigestCron();

  // 1. Каждый понедельник в 10:00 — еженедельный дайджест
  digestTask = cron.schedule('0 10 * * 1', async () => {
    console.log('[Cron] Running weekly digest broadcast (0 10 * * 1)...');
    await runWeeklyDigestBroadcast({ force: false });
  });

  // 2. Каждый день в 03:00 — очистка истекших сессий и старых кодов привязки Telegram
  cleanupTask = cron.schedule('0 3 * * *', async () => {
    console.log('[Cron] Running daily maintenance cleanup (0 3 * * *)...');
    await runMaintenanceCleanup().catch((err) => {
      console.error('[Cron] Maintenance cleanup failed:', err);
    });
  });

  // 3. Каждую пятницу в 17:00 — напоминание о несданных ДЗ
  reminderTask = cron.schedule('0 17 * * 5', async () => {
    console.log('[Cron] Running homework reminders broadcast (0 17 * * 5)...');
    await runHomeworkRemindersBroadcast().catch((err) => {
      console.error('[Cron] Homework reminders failed:', err);
    });
  });
}

export function stopWeeklyDigestCron(): void {
  if (digestTask) {
    digestTask.stop();
    digestTask = null;
  }
  if (cleanupTask) {
    cleanupTask.stop();
    cleanupTask = null;
  }
  if (reminderTask) {
    reminderTask.stop();
    reminderTask = null;
  }
}
