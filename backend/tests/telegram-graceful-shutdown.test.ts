import test from 'node:test';
import assert from 'node:assert/strict';
import {
  stopTelegramBot,
  launchBotWithRetry,
} from '../src/services/telegramService.js';

test('Telegram Graceful Shutdown: stopTelegramBot handles stopped and uninitialized states safely', async () => {
  // Вызов остановки, когда бот не активен или уже остановлен, не должен выбрасывать исключений
  await assert.doesNotReject(async () => {
    await stopTelegramBot('TEST_SHUTDOWN');
  });
});

test('launchBotWithRetry: retries on 409 Conflict and succeeds after conflict resolves', async () => {
  let callCount = 0;

  // Мокаем Telegraf инстанс
  const mockBot = {
    telegram: {
      deleteWebhook: async () => true,
    },
    launch: async () => {
      callCount++;
      if (callCount < 3) {
        // Симулируем 409 Conflict на попытках 1 и 2
        throw new Error('409: Conflict: terminated by other getUpdates request; make sure that only one bot instance is running');
      }
      // На 3-й попытке старый контейнер Render завершился, поллинг успешен
      return true;
    },
  } as any;

  // Запуск с максимальным числом попыток 4 и быстрой задержкой для тестов (10ms)
  const result = await launchBotWithRetry(mockBot, 4, 10);
  assert.equal(result, true);
  assert.equal(callCount, 3);
});

test('launchBotWithRetry: returns false gracefully when all retry attempts fail', async () => {
  let attempts = 0;

  const failingBot = {
    telegram: {
      deleteWebhook: async () => true,
    },
    launch: async () => {
      attempts++;
      throw new Error('409: Conflict: persistent conflict');
    },
  } as any;

  const result = await launchBotWithRetry(failingBot, 2, 10);
  assert.equal(result, false);
  assert.equal(attempts, 2);
});
