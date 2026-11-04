import { Readable } from 'node:stream';
import { Telegraf } from 'telegraf';
import { Role, SubmissionStatus } from '@prisma/client';
import { prisma } from '../prisma.js';
import { config } from '../config.js';
import { checkAndAwardAcceptedSubmission } from './achievements.js';
import { runWeeklyDigestBroadcast } from './cronService.js';

let bot: Telegraf | null = null;
let isBotActive = false;

export function getTelegramBotStatus(): 'active' | 'disabled' | 'starting' {
  if (!isTelegramTokenConfigured()) return 'disabled';
  return isBotActive ? 'active' : 'starting';
}

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

/**
 * Проверяет, что Telegram Chat ID состоит только из цифр (с поддержкой отрицательных значений для групп/супергрупп).
 */
export function isValidTelegramChatId(chatId?: string | number | null): boolean {
  if (chatId === null || chatId === undefined) return false;
  const str = String(chatId).trim();
  return /^-?\d+$/.test(str);
}

/**
 * Вспомогательный метод привязки Telegram Chat ID ментора с валидацией роли ADMIN и уникальности.
 */
export async function bindMentorTelegramChatId(
  mentorLoginOrId: string,
  telegramChatId: string | number
): Promise<{
  ok: boolean;
  user?: { id: string; login: string; telegramChatId: string | null };
  error?: string;
}> {
  const cleanChatId = String(telegramChatId).trim();
  if (!isValidTelegramChatId(cleanChatId)) {
    return {
      ok: false,
      error: 'Telegram Chat ID должен состоять только из цифр (с возможным знаком минус для групп/каналов)',
    };
  }

  const mentor = await prisma.user.findFirst({
    where: {
      OR: [
        { id: mentorLoginOrId },
        { login: mentorLoginOrId },
      ],
    },
  });

  if (!mentor) {
    return { ok: false, error: 'Пользователь не найден' };
  }

  if (mentor.role !== Role.ADMIN) {
    return {
      ok: false,
      error: 'Пользователь не является ментором/администратором (роль должна быть ADMIN)',
    };
  }

  const existingWithChatId = await prisma.user.findFirst({
    where: {
      telegramChatId: cleanChatId,
      NOT: { id: mentor.id },
    },
  });

  if (existingWithChatId) {
    return {
      ok: false,
      error: `Этот Telegram Chat ID уже привязан к другому пользователю: @${existingWithChatId.login}`,
    };
  }

  const updated = await prisma.user.update({
    where: { id: mentor.id },
    data: { telegramChatId: cleanChatId },
    select: { id: true, login: true, telegramChatId: true },
  });

  return { ok: true, user: updated };
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
  // В тестовом окружении реальные сетевые сообщения в Telegram глушатся
  if (process.env.NODE_ENV === 'test') {
    return true;
  }

  const activeBot = getActiveBotInstance();
  if (!activeBot || !chatId || chatId === 'your_channel_or_group_id' || !isValidTelegramChatId(chatId)) {
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

    if (!user?.telegramChatId || !isValidTelegramChatId(user.telegramChatId)) {
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
  // В тестовом окружении реальные сетевые вызовы к Telegram глушатся
  if (process.env.NODE_ENV === 'test') {
    return true;
  }

  const activeBot = getActiveBotInstance();
  if (!activeBot || !voiceFileId) {
    return false;
  }

  try {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { telegramChatId: true },
    });

    if (!user?.telegramChatId || !isValidTelegramChatId(user.telegramChatId)) {
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
          groupNumber: true,
          mentor: {
            select: {
              id: true,
              telegramChatId: true,
            },
          },
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

  // Если у студента есть персональный ментор с привязанным Telegram — отправляем только ему.
  // Иначе — фолбэк на всех активных менторов платформы.
  let mentors: { id: string; telegramChatId: string | null }[] = [];
  if (submission.user.mentor?.telegramChatId) {
    mentors = [submission.user.mentor];
  } else {
    mentors = await prisma.user.findMany({
      where: {
        role: Role.ADMIN,
        telegramChatId: { not: null },
      },
      select: {
        id: true,
        telegramChatId: true,
      },
    });
  }

  if (mentors.length === 0) {
    return null;
  }

  // В тестовом окружении реальные сетевые сообщения в Telegram менторам глушатся
  if (process.env.NODE_ENV === 'test') {
    const mockMsgId = `mock_tg_msg_${Date.now()}`;
    await prisma.submission.update({
      where: { id: submission.id },
      data: { mentorTelegramMsgId: mockMsgId },
    });
    return mockMsgId;
  }

  const activeBot = getActiveBotInstance();
  if (!activeBot) {
    return null;
  }

  const studentDisplayName = escapeTelegramHtml(submission.user.name || submission.user.login);
  const studentLogin = escapeTelegramHtml(submission.user.login);
  const taskTitle = escapeTelegramHtml(submission.task.title);
  const repoUrl = escapeTelegramHtml(submission.solutionLink);
  const groupBadge = submission.user.groupNumber ? ` (Группа ${escapeTelegramHtml(submission.user.groupNumber)})` : '';

  const text = [
    '📬 <b>Новое ДЗ на проверку!</b>',
    `Студент: <b>${studentDisplayName} (@${studentLogin})</b>${groupBadge}`,
    `Задание: <b>${taskTitle}</b>`,
    `Репозиторий: <a href="${repoUrl}">${repoUrl}</a>`,
    '',
    '<i>Нажмите кнопку действия ниже или ответьте (Reply) на это сообщение с замечаниями.</i>',
  ].join('\n');

  let lastMsgId: string | null = null;

  for (const mentor of mentors) {
    if (!mentor.telegramChatId) continue;
    if (!isValidTelegramChatId(mentor.telegramChatId)) {
      console.warn(`[Telegram] Skipping mentor ${mentor.id} with non-numeric telegramChatId: ${mentor.telegramChatId}`);
      continue;
    }
    try {
      const sent = await activeBot.telegram.sendMessage(mentor.telegramChatId, text, {
        parse_mode: 'HTML',
        reply_markup: {
          inline_keyboard: [
            [
              {
                text: '🔗 Открыть GitHub',
                url: submission.solutionLink,
              },
            ],
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

  // Строгая авторизация: если передан mentorChatId, ментор обязан существовать в БД и иметь роль ADMIN
  let mentor: { id: string; login: string; name: string | null } | null = null;
  if (mentorChatId) {
    mentor = await prisma.user.findFirst({
      where: {
        telegramChatId: String(mentorChatId),
        role: Role.ADMIN,
      },
      select: { id: true, login: true, name: true },
    });

    if (!mentor) {
      return { ok: false, error: '⛔ Доступ запрещен: вы не являетесь ментором платформы' };
    }
  }

  if (action === 'accept') {
    // Идемпотентность: защита от повторного клика
    if (submission.status === SubmissionStatus.ACCEPTED) {
      return { ok: false, error: '⚠️ Это задание уже принято ранее' };
    }

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
      ...(mentor ? [`Проверил: <b>@${escapeTelegramHtml(mentor.login)}</b>`] : []),
    ].join('\n');

    await sendTelegramNotification(submission.userId, studentMsg);

    const mentorSuffix = mentor ? ` ментором @${mentor.login}` : '';
    return {
      ok: true,
      status: SubmissionStatus.ACCEPTED,
      score: maxScore,
      statusText: `✅ Принято (${maxScore} / ${maxScore} баллов)${mentorSuffix}`,
    };
  }

  // action === 'reject' -> ДВУХФАЗНЫЙ СЦЕНАРИЙ:
  // 1. Статус переводится в IN_REVIEW («В процессе проверки»)
  // 2. Закрепляется ментор (если передан)
  // 3. Ментор досылает замечания (текст/войс) через Reply, после чего статус переходит в REVISION
  await prisma.submission.update({
    where: { id: submission.id },
    data: {
      status: SubmissionStatus.IN_REVIEW,
      ...(mentor ? { reviewer: { connect: { id: mentor.id } } } : {}),
    },
  });

  const mentorSuffix = mentor ? ` ментором @${mentor.login}` : '';
  return {
    ok: true,
    status: SubmissionStatus.IN_REVIEW,
    statusText: `⏳ В процессе проверки${mentorSuffix}`,
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

  // Строгая проверка прав ментора: если передан mentorChatId, проверяем роль ADMIN в БД
  let mentor: { id: string; login: string; name: string | null } | null = null;
  if (mentorChatId) {
    mentor = await prisma.user.findFirst({
      where: {
        telegramChatId: String(mentorChatId),
        role: Role.ADMIN,
      },
      select: { id: true, login: true, name: true },
    });

    if (!mentor) {
      return { ok: false, error: '⛔ Только авторизованный ментор платформы может отправлять фидбек' };
    }
  }

  // При получении замечаний работа переводится в REVISION («На доработку»)
  const updateData: {
    status: SubmissionStatus;
    reviewedAt: Date;
    reviewerComment?: string;
    voiceFeedbackUrl?: string;
    reviewerId?: string;
  } = {
    status: SubmissionStatus.REVISION,
    reviewedAt: new Date(),
    ...(mentor ? { reviewerId: mentor.id } : {}),
  };

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

  const maxScore = submission.task.maxScore ?? 10;
  const displayScore = updated.score ?? 0;

  if (textFeedback && textFeedback.trim()) {
    const msg = [
      '📝 <b>Ментор проверил ваше ДЗ и отправил на доработку!</b>',
      `Задание: <b>${escapeTelegramHtml(submission.task.title)}</b>`,
      'Статус: <b>🔄 На доработку</b>',
      `Баллы: <b>${displayScore} / ${maxScore}</b>`,
      `Замечания ментора: <i>${escapeTelegramHtml(textFeedback.trim())}</i>`,
    ].join('\n');

    await sendTelegramNotification(submission.userId, msg);
  }

  if (voiceFileId && voiceFileId.trim()) {
    const caption = [
      '🎙 <b>Ментор оставил голосовой фидбек к вашей работе (на доработку)</b>',
      `Задание: <b>${escapeTelegramHtml(submission.task.title)}</b>`,
      'Статус: <b>🔄 На доработку</b>',
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

/**
 * Получает потоковый доступ к аудиофайлу из Telegram API по его file_id для воспроизведения в веб-интерфейсе.
 */
export async function getTelegramFileStream(fileId: string): Promise<{
  stream: NodeJS.ReadableStream;
  contentType: string;
} | null> {
  // В тестовом окружении для синтетических ID возвращаем стрим из памяти
  if (process.env.NODE_ENV === 'test' && fileId.startsWith('mock_voice_')) {
    const mockAudioBuffer = Buffer.from('OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00mock_opus_audio_payload');
    return {
      stream: Readable.from(mockAudioBuffer),
      contentType: 'audio/ogg',
    };
  }

  const activeBot = getActiveBotInstance();
  if (!activeBot || !fileId) {
    return null;
  }

  try {
    const fileLink = await activeBot.telegram.getFileLink(fileId);
    const response = await fetch(fileLink.href);
    if (!response.ok || !response.body) {
      return null;
    }

    const contentType = response.headers.get('content-type') || 'audio/ogg';
    const nodeStream = (response.body as any).pipe
      ? (response.body as any)
      : Readable.fromWeb(response.body as any);

    return { stream: nodeStream, contentType };
  } catch (err) {
    console.warn(`[Telegram] Failed to get file stream for ${fileId}:`, (err as Error)?.message || err);
    return null;
  }
}

/**
 * Безопасно останавливает polling Telegram-бота и освобождает ресурсы.
 */
export async function stopTelegramBot(reason = 'SIGTERM'): Promise<void> {
  if (!bot) {
    return;
  }
  try {
    if (isBotActive) {
      console.log(`[Telegram] Stopping bot polling (reason: ${reason})...`);
      isBotActive = false;
      bot.stop(reason);
      console.log('[Telegram] Bot polling stopped successfully.');
    }
  } catch (err: unknown) {
    const msg = (err as Error)?.message || String(err);
    if (!msg.includes('Bot is not running')) {
      console.warn('[Telegram] Warning while stopping bot:', msg);
    }
  }
}

/**
 * Запускает polling бота с Exponential Retry Backoff при ошибке 409 Conflict и сбоях сети.
 * Это предотвращает крах бота при деплоях на Render, когда старый контейнер еще удерживает getUpdates.
 */
export async function launchBotWithRetry(
  botInstance: Telegraf,
  maxAttempts = 5,
  initialDelayMs = 2000
): Promise<boolean> {
  let attempt = 0;
  let delayMs = initialDelayMs;

  while (attempt < maxAttempts) {
    attempt++;
    try {
      try {
        await botInstance.telegram.deleteWebhook({ drop_pending_updates: false });
      } catch {
        // Игнорируем сетевые ошибки на удалении вебхука
      }

      await botInstance.launch();
      isBotActive = true;
      console.log(`[Telegram] Bot successfully started polling (attempt ${attempt})`);
      return true;
    } catch (err: unknown) {
      isBotActive = false;
      const errorMsg = (err as Error)?.message || String(err);
      const is409 = errorMsg.includes('409') || errorMsg.includes('Conflict');

      if (is409 && attempt < maxAttempts) {
        console.warn(
          `[Telegram] 409 Conflict: previous bot instance is still active on Render. Waiting ${delayMs}ms before retry (attempt ${attempt}/${maxAttempts})...`
        );
        await new Promise((resolve) => setTimeout(resolve, delayMs));
        delayMs = Math.min(delayMs * 2, 16000);
        continue;
      }

      console.warn(`[Telegram] Failed to launch bot polling on attempt ${attempt}:`, errorMsg);
      if (
        attempt < maxAttempts &&
        (errorMsg.includes('ETIMEDOUT') ||
          errorMsg.includes('ECONNRESET') ||
          errorMsg.includes('ENOTFOUND'))
      ) {
        console.log(`[Telegram] Network timeout. Retrying in ${delayMs}ms...`);
        await new Promise((resolve) => setTimeout(resolve, delayMs));
        delayMs = Math.min(delayMs * 2, 16000);
        continue;
      }

      break;
    }
  }

  return false;
}

export function initTelegramBot(): Telegraf | null {
  const token = config.telegram.botToken.trim();

  if (!isTelegramTokenConfigured(token)) {
    console.warn(
      '[Telegram] TELEGRAM_BOT_TOKEN is not set or uses placeholder. Telegram notifications are disabled.'
    );
    return null;
  }

  // Синглтон-гард: если бот уже был создан, останавливаем предыдущий
  if (bot && isBotActive) {
    stopTelegramBot('REINIT').catch(() => {});
  }

  try {
    bot = new Telegraf(token);

    // Глобальный перехватчик необработанных ошибок Telegraf
    bot.catch((err, ctx) => {
      const updateId = ctx?.update?.update_id ?? 'unknown';
      console.error(
        `[Telegram] Unhandled error while processing update ${updateId}:`,
        (err as Error)?.message || err
      );
    });

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

    // Команда /digest для запуска еженедельного дайджеста вручную (только для менторов/админов)
    bot.command('digest', async (ctx) => {
      try {
        const callerChatId = ctx.chat?.id ? String(ctx.chat.id) : (ctx.from?.id ? String(ctx.from.id) : undefined);
        if (!callerChatId) {
          await ctx.reply('❌ Не удалось определить ваш Telegram Chat ID.');
          return;
        }

        const callerUser = await prisma.user.findFirst({
          where: {
            telegramChatId: callerChatId,
            role: Role.ADMIN,
          },
        });

        if (!callerUser) {
          await ctx.reply('⛔ Команда /digest доступна только администраторам и менторам курса.');
          return;
        }

        await ctx.reply('⏳ Формирую и рассылаю еженедельный дайджест...');
        const result = await runWeeklyDigestBroadcast({ force: true });
        if (result.message) {
          await ctx.reply(
            `✅ Дайджест сформирован и разослан (${result.sentToUsersCount} получателям).`
          );
        } else {
          await ctx.reply('⚠️ Не удалось разослать дайджест или список получателей пуст.');
        }
      } catch (err) {
        console.error('[Telegram] Error handling /digest command:', err);
        await ctx.reply('❌ Произошла ошибка при запуске дайджеста.');
      }
    });

    // Обработка Inline-кнопок ментора: sub_accept:<id> и sub_reject:<id>
    bot.action(/^sub_(accept|reject):(.+)$/, async (ctx) => {
      try {
        const action = ctx.match[1] as 'accept' | 'reject';
        const submissionId = ctx.match[2];
        const mentorChatId = ctx.chat?.id ? String(ctx.chat.id) : (ctx.from?.id ? String(ctx.from.id) : undefined);

        const result = await processMentorCallbackDecision({
          action,
          submissionId,
          mentorChatId,
        });

        if (!result.ok) {
          await ctx.answerCbQuery(result.error || 'Ошибка обработки', { show_alert: true });
          return;
        }

        await ctx.answerCbQuery(action === 'accept' ? '✅ Принято!' : '⏳ Ожидание замечаний...');

        // Редактируем исходное сообщение ментора (убираем кнопки и фиксируем статус)
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
        const mentorChatId = ctx.chat?.id ? String(ctx.chat.id) : (ctx.from?.id ? String(ctx.from.id) : undefined);
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
            await ctx.reply('✅ Замечания сохранены и отправлены студенту!');
          }
        } else if (result.error && !result.error.includes('Не найдена')) {
          await ctx.reply(result.error);
        }
      } catch (err) {
        console.error('[Telegram] Error handling mentor reply message:', err);
      }
    });

    // Асинхронный запуск с retry backoff при 409 Conflict
    launchBotWithRetry(bot).catch((err) => {
      console.warn('[Telegram] Background polling failed:', (err as Error)?.message || err);
    });

    const onSignal = (sig: string) => {
      stopTelegramBot(sig).catch(() => {});
    };
    process.once('SIGINT', () => onSignal('SIGINT'));
    process.once('SIGTERM', () => onSignal('SIGTERM'));

    return bot;
  } catch (err) {
    console.warn('[Telegram] Error initializing Telegraf instance:', err);
    bot = null;
    return null;
  }
}
