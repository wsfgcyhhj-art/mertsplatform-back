import { Telegraf } from 'telegraf';
import { Role, SubmissionStatus } from '@prisma/client';
import { prisma } from '../prisma.js';
import { config } from '../config.js';
import { checkAndAwardAcceptedSubmission } from './achievements.js';
import { runWeeklyDigestBroadcast } from './cronService.js';

let bot: Telegraf | null = null;
let isBotActive = false;

export function isTelegramTokenConfigured(token?: string): boolean {
  const raw = (token ?? config.telegram.botToken ?? '').trim();
  return Boolean(raw && raw !== 'your_bot_token_here');
}

export function escapeTelegramHtml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function getActiveBotInstance(): Telegraf | null {
  if (!isTelegramTokenConfigured()) {
    return null;
  }
  return bot ?? new Telegraf(config.telegram.botToken.trim());
}

export async function sendTelegramMessageToChatId(
  chatId: string,
  text: string
): Promise<boolean> {
  const activeBot = getActiveBotInstance();
  if (!activeBot || !chatId || chatId === 'your_channel_or_group_id') {
    return false;
  }

  try {
    await activeBot.telegram.sendMessage(chatId, text, {
      parse_mode: 'HTML',
    });
    return true;
  } catch (err: unknown) {
    const status = (err as { response?: { error_code?: number } })?.response?.error_code;
    if (status === 403) {
      console.warn(`[Telegram] Chat ${chatId} blocked the bot (403 Forbidden).`);
    } else {
      console.warn(`[Telegram] Failed to send message to chat ${chatId}:`, (err as Error)?.message || err);
    }
    return false;
  }
}

export async function sendTelegramNotification(
  userId: string,
  text: string
): Promise<boolean> {
  if (!isTelegramTokenConfigured()) {
    return false;
  }

  try {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { telegramChatId: true },
    });

    if (!user?.telegramChatId) {
      return false;
    }

    return await sendTelegramMessageToChatId(user.telegramChatId, text);
  } catch (err: unknown) {
    console.warn(`[Telegram] Failed to send notification to user ${userId}:`, (err as Error)?.message || err);
    return false;
  }
}

export async function sendTelegramVoiceNotification(
  userId: string,
  voiceFileId: string,
  caption?: string
): Promise<boolean> {
  const activeBot = getActiveBotInstance();
  if (!activeBot || !voiceFileId) {
    return false;
  }

  try {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { telegramChatId: true },
    });

    if (!user?.telegramChatId) {
      return false;
    }

    await activeBot.telegram.sendVoice(user.telegramChatId, voiceFileId, {
      caption,
      parse_mode: 'HTML',
    });
    return true;
  } catch (err: unknown) {
    console.warn(`[Telegram] Failed to send voice to user ${userId}:`, (err as Error)?.message || err);
    return false;
  }
}

/**
 * Уведомляет всех менторов (Role.ADMIN с привязанным telegramChatId) о новой сдаче ДЗ
 * с Inline-кнопками [ ✅ Принять (макс. балл) ] и [ 🔄 На доработку ]
 * и сохраняет ID сообщения в submission.mentorTelegramMsgId.
 */
export async function notifyMentorsNewSubmission(
  submissionId: string
): Promise<string | null> {
  const submission = await prisma.submission.findUnique({
    where: { id: submissionId },
    include: {
      user: {
        select: {
          id: true,
          name: true,
          login: true,
        },
      },
      task: {
        select: {
          id: true,
          title: true,
          maxScore: true,
        },
      },
    },
  });

  if (!submission) {
    return null;
  }

  const mentors = await prisma.user.findMany({
    where: {
      role: Role.ADMIN,
      telegramChatId: { not: null },
    },
    select: {
      id: true,
      telegramChatId: true,
    },
  });

  if (mentors.length === 0) {
    return null;
  }

  const activeBot = getActiveBotInstance();
  if (!activeBot) {
    return null;
  }

  const studentDisplayName = escapeTelegramHtml(submission.user.name || submission.user.login);
  const studentLogin = escapeTelegramHtml(submission.user.login);
  const taskTitle = escapeTelegramHtml(submission.task.title);
  const repoUrl = escapeTelegramHtml(submission.solutionLink);

  const text = [
    '📬 <b>Новое ДЗ на проверку!</b>',
    `Студент: <b>${studentDisplayName} (@${studentLogin})</b>`,
    `Задание: <b>${taskTitle}</b>`,
    `Репозиторий: <a href="${repoUrl}">${repoUrl}</a>`,
    '',
    '<i>Нажмите кнопку ниже или ответьте (Reply) на это сообщение с текстом/войсом замечаний.</i>',
  ].join('\n');

  let lastMsgId: string | null = null;

  for (const mentor of mentors) {
    if (!mentor.telegramChatId) continue;
    try {
      const sent = await activeBot.telegram.sendMessage(mentor.telegramChatId, text, {
        parse_mode: 'HTML',
        reply_markup: {
          inline_keyboard: [
            [
              {
                text: '✅ Принять (макс. балл)',
                callback_data: `sub_accept:${submission.id}`,
              },
              {
                text: '🔄 На доработку',
                callback_data: `sub_reject:${submission.id}`,
              },
            ],
          ],
        },
      });
      lastMsgId = String(sent.message_id);
    } catch (err) {
      console.warn(`[Telegram] Failed to notify mentor ${mentor.id}:`, (err as Error)?.message || err);
    }
  }

  if (lastMsgId) {
    await prisma.submission.update({
      where: { id: submission.id },
      data: { mentorTelegramMsgId: lastMsgId },
    });
  }

  return lastMsgId;
}

/**
 * Бизнес-логика обработки нажатия ментором Inline-кнопки в Telegram (`sub_accept:<id>` или `sub_reject:<id>`).
 */
export async function processMentorCallbackDecision(params: {
  action: 'accept' | 'reject';
  submissionId: string;
  mentorChatId?: string;
}): Promise<{
  ok: boolean;
  status?: SubmissionStatus;
  score?: number | null;
  statusText?: string;
  error?: string;
}> {
  const { action, submissionId, mentorChatId } = params;

  const submission = await prisma.submission.findUnique({
    where: { id: submissionId },
    include: {
      task: true,
      user: true,
    },
  });

  if (!submission) {
    return { ok: false, error: 'Сдача ДЗ не найдена' };
  }

  const mentor = mentorChatId
    ? await prisma.user.findUnique({
        where: { telegramChatId: String(mentorChatId) },
        select: { id: true },
      })
    : null;

  if (action === 'accept') {
    const maxScore = submission.task.maxScore ?? 10;
    const updated = await prisma.submission.update({
      where: { id: submission.id },
      data: {
        status: SubmissionStatus.ACCEPTED,
        score: maxScore,
        reviewedAt: new Date(),
        ...(mentor ? { reviewer: { connect: { id: mentor.id } } } : {}),
      },
    });

    await checkAndAwardAcceptedSubmission(
      submission.userId,
      submission.taskId,
      updated.score
    );

    const studentMsg = [
      '📝 <b>Ментор проверил ваше ДЗ!</b>',
      `Задание: <b>${escapeTelegramHtml(submission.task.title)}</b>`,
      'Статус: <b>✅ Принято</b>',
      `Баллы: <b>${maxScore} / ${maxScore}</b>`,
    ].join('\n');

    await sendTelegramNotification(submission.userId, studentMsg);

    return {
      ok: true,
      status: SubmissionStatus.ACCEPTED,
      score: maxScore,
      statusText: `✅ Принято (${maxScore} / ${maxScore} баллов)`,
    };
  }

  // action === 'reject' -> REVISION (На доработку)
  await prisma.submission.update({
    where: { id: submission.id },
    data: {
      status: SubmissionStatus.REVISION,
      reviewedAt: new Date(),
      ...(mentor ? { reviewer: { connect: { id: mentor.id } } } : {}),
    },
  });

  const maxScore = submission.task.maxScore ?? 10;
  const studentMsg = [
    '📝 <b>Ментор проверил ваше ДЗ!</b>',
    `Задание: <b>${escapeTelegramHtml(submission.task.title)}</b>`,
    'Статус: <b>🔄 На доработку</b>',
    `Баллы: <b>${submission.score ?? 0} / ${maxScore}</b>`,
    '<i>Ментор скоро пришлет комментарий с замечаниями.</i>',
  ].join('\n');

  await sendTelegramNotification(submission.userId, studentMsg);

  return {
    ok: true,
    status: SubmissionStatus.REVISION,
    score: submission.score ?? 0,
    statusText: '🔄 Отправлено на доработку',
  };
}

/**
 * Бизнес-логика обработки ответа (Reply) ментора на карточку ДЗ (текстом или голосовым сообщением).
 */
export async function processMentorReplyFeedback(params: {
  replyToMessageId: string;
  mentorChatId?: string;
  textFeedback?: string;
  voiceFileId?: string;
}): Promise<{
  ok: boolean;
  submissionId?: string;
  status?: SubmissionStatus;
  error?: string;
}> {
  const { replyToMessageId, mentorChatId, textFeedback, voiceFileId } = params;

  const submission = await prisma.submission.findFirst({
    where: { mentorTelegramMsgId: String(replyToMessageId) },
    include: {
      task: true,
      user: true,
    },
  });

  if (!submission) {
    return { ok: false, error: 'Не найдена сдача ДЗ, привязанная к этому сообщению' };
  }

  const mentor = mentorChatId
    ? await prisma.user.findUnique({
        where: { telegramChatId: String(mentorChatId) },
        select: { id: true },
      })
    : null;

  // Умная связка: если ментор делает Reply на ещё не проверенную работу (SENT / IN_REVIEW),
  // автоматически переводим её в REVISION («На доработку»). Если уже ACCEPTED/REVISION — сохраняем статус.
  const nextStatus =
    submission.status === SubmissionStatus.ACCEPTED
      ? SubmissionStatus.ACCEPTED
      : SubmissionStatus.REVISION;

  const updateData: {
    status: SubmissionStatus;
    reviewedAt: Date;
    reviewerComment?: string;
    voiceFeedbackUrl?: string;
    reviewerId?: string;
  } = {
    status: nextStatus,
    reviewedAt: new Date(),
  };

  if (mentor?.id) {
    updateData.reviewerId = mentor.id;
  }

  if (textFeedback && textFeedback.trim()) {
    updateData.reviewerComment = textFeedback.trim();
  }

  if (voiceFileId && voiceFileId.trim()) {
    updateData.voiceFeedbackUrl = voiceFileId.trim();
  }

  const updated = await prisma.submission.update({
    where: { id: submission.id },
    data: updateData,
  });

  const statusLabel =
    updated.status === SubmissionStatus.ACCEPTED ? '✅ Принято' : '🔄 На доработку';
  const maxScore = submission.task.maxScore ?? 10;
  const displayScore = updated.score ?? 0;

  if (textFeedback && textFeedback.trim()) {
    const msg = [
      '📝 <b>Ментор проверил ваше ДЗ!</b>',
      `Задание: <b>${escapeTelegramHtml(submission.task.title)}</b>`,
      `Статус: <b>${statusLabel}</b>`,
      `Баллы: <b>${displayScore} / ${maxScore}</b>`,
      `Комментарий: <i>${escapeTelegramHtml(textFeedback.trim())}</i>`,
    ].join('\n');

    await sendTelegramNotification(submission.userId, msg);
  }

  if (voiceFileId && voiceFileId.trim()) {
    const caption = [
      '🎙 <b>Ментор оставил голосовой фидбек к вашей работе!</b>',
      `Задание: <b>${escapeTelegramHtml(submission.task.title)}</b>`,
      `Статус: <b>${statusLabel}</b>`,
    ].join('\n');

    const voiceSent = await sendTelegramVoiceNotification(
      submission.userId,
      voiceFileId.trim(),
      caption
    );

    if (!voiceSent) {
      await sendTelegramNotification(submission.userId, caption);
    }
  }

  return {
    ok: true,
    submissionId: updated.id,
    status: updated.status,
  };
}

export function initTelegramBot(): Telegraf | null {
  const token = config.telegram.botToken.trim();

  if (!isTelegramTokenConfigured(token)) {
    console.warn(
      '[Telegram] TELEGRAM_BOT_TOKEN is not set or uses placeholder. Telegram notifications are disabled.'
    );
    return null;
  }

  try {
    bot = new Telegraf(token);

    bot.start(async (ctx) => {
      try {
        const messageText = 'text' in (ctx.message || {}) ? (ctx.message as { text: string }).text : '';
        const code = (ctx.startPayload || messageText.split(/\s+/)[1] || '').trim();

        if (!code) {
          await ctx.reply(
            'Для привязки аккаунта перейдите в профиль на платформе и нажмите кнопку "Подключить Telegram"'
          );
          return;
        }

        const user = await prisma.user.findUnique({
          where: { telegramAuthCode: code },
        });

        if (!user) {
          await ctx.reply(
            'Для привязки аккаунта перейдите в профиль на платформе и нажмите кнопку "Подключить Telegram"'
          );
          return;
        }

        const chatId = String(ctx.chat.id);
        const username = ctx.from?.username || null;

        await prisma.user.updateMany({
          where: {
            telegramChatId: chatId,
            NOT: { id: user.id },
          },
          data: {
            telegramChatId: null,
          },
        });

        await prisma.user.update({
          where: { id: user.id },
          data: {
            telegramChatId: chatId,
            telegramUsername: username,
            telegramAuthCode: null,
          },
        });

        await ctx.reply(
          '🎉 Аккаунт успешно привязан к MertsPlatform! Теперь сюда будут приходить уведомления о проверке ДЗ, новых уроках и ачивках.'
        );
      } catch (err) {
        console.error('[Telegram] Error handling /start command:', err);
      }
    });

    // Команда /digest для запуска еженедельного дайджеста вручную
    bot.command('digest', async (ctx) => {
      try {
        const result = await runWeeklyDigestBroadcast();
        if (result.message) {
          await ctx.reply(
            `✅ Дайджест сформирован и разослан (${result.sentToUsersCount} получателям).`
          );
        }
      } catch (err) {
        console.error('[Telegram] Error handling /digest command:', err);
      }
    });

    // Обработка Inline-кнопок ментора: sub_accept:<id> и sub_reject:<id>
    bot.action(/^sub_(accept|reject):(.+)$/, async (ctx) => {
      try {
        const action = ctx.match[1] as 'accept' | 'reject';
        const submissionId = ctx.match[2];
        const mentorChatId = ctx.chat?.id ? String(ctx.chat.id) : undefined;

        const result = await processMentorCallbackDecision({
          action,
          submissionId,
          mentorChatId,
        });

        if (!result.ok) {
          await ctx.answerCbQuery(result.error || 'Ошибка обработки');
          return;
        }

        await ctx.answerCbQuery(result.statusText || 'Готово');

        // Редактируем исходное сообщение ментора (убираем кнопки и добавляем статус)
        const originalMsg = ctx.callbackQuery.message;
        if (originalMsg && 'text' in originalMsg) {
          const updatedText = `${originalMsg.text}\n\n${result.statusText}`;
          await ctx.editMessageText(updatedText, {
            reply_markup: { inline_keyboard: [] },
          });
        }

        if (action === 'reject') {
          await ctx.reply(
            '✏️ Ответьте (Reply) на сообщение с этим ДЗ текстом или голосовым сообщением, чтобы отправить замечания студенту.'
          );
        }
      } catch (err) {
        console.error('[Telegram] Error handling mentor callback_query:', err);
      }
    });

    // Обработка Reply от ментора (текстом или голосовым сообщением)
    bot.on('message', async (ctx) => {
      try {
        const msg = ctx.message as {
          reply_to_message?: { message_id: number };
          text?: string;
          voice?: { file_id: string };
        };

        if (!msg?.reply_to_message?.message_id) {
          return;
        }

        const replyToMessageId = String(msg.reply_to_message.message_id);
        const mentorChatId = ctx.chat?.id ? String(ctx.chat.id) : undefined;
        const textFeedback = msg.text;
        const voiceFileId = msg.voice?.file_id;

        if (!textFeedback && !voiceFileId) {
          return;
        }

        const result = await processMentorReplyFeedback({
          replyToMessageId,
          mentorChatId,
          textFeedback,
          voiceFileId,
        });

        if (result.ok) {
          if (voiceFileId) {
            await ctx.reply('🎤 Голосовой фидбек сохранен и отправлен студенту!');
          } else {
            await ctx.reply('✅ Комментарий сохранен и отправлен студенту!');
          }
        }
      } catch (err) {
        console.error('[Telegram] Error handling mentor reply message:', err);
      }
    });

    bot
      .launch()
      .then(() => {
        isBotActive = true;
        console.log('[Telegram] Bot successfully started polling');
      })
      .catch((err) => {
        isBotActive = false;
        console.warn('[Telegram] Failed to launch bot polling (continuing without bot):', err?.message || err);
      });

    process.once('SIGINT', () => {
      if (bot && isBotActive) bot.stop('SIGINT');
    });
    process.once('SIGTERM', () => {
      if (bot && isBotActive) bot.stop('SIGTERM');
    });

    return bot;
  } catch (err) {
    console.warn('[Telegram] Error initializing Telegraf instance:', err);
    bot = null;
    return null;
  }
}
