import { Telegraf } from 'telegraf';
import { prisma } from '../prisma.js';
import { config } from '../config.js';

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

        // Освобождаем chatId, если он ранее был привязан к другому аккаунту
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

    const activeBot = bot ?? new Telegraf(config.telegram.botToken.trim());
    await activeBot.telegram.sendMessage(user.telegramChatId, text, {
      parse_mode: 'HTML',
    });

    return true;
  } catch (err: unknown) {
    const status = (err as { response?: { error_code?: number } })?.response?.error_code;
    if (status === 403) {
      console.warn(`[Telegram] User ${userId} blocked the bot (403 Forbidden). Skipping notification.`);
    } else {
      console.warn(`[Telegram] Failed to send notification to user ${userId}:`, (err as Error)?.message || err);
    }
    return false;
  }
}
