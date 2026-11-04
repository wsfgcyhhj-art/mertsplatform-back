import { prisma } from '../src/prisma.js';
import { bindMentorTelegramChatId, isValidTelegramChatId } from '../src/services/telegramService.js';

/**
 * CLI-скрипт для привязки Telegram Chat ID ментору платформы.
 * Использование:
 *   npx tsx scripts/bind-mentor-chat-id.ts <login_или_userId> <telegram_chat_id>
 * Пример:
 *   npx tsx scripts/bind-mentor-chat-id.ts admin 123456789
 *   npx tsx scripts/bind-mentor-chat-id.ts ular -1001234567890
 */
async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error('❌ Ошибка: недостаточно аргументов.');
    console.log('Использование: npx tsx scripts/bind-mentor-chat-id.ts <login_или_userId> <telegram_chat_id>');
    process.exit(1);
  }

  const [mentorLoginOrId, rawChatId] = args;

  if (!isValidTelegramChatId(rawChatId)) {
    console.error('❌ Ошибка: Chat ID должен состоять только из цифр (с возможным знаком минус для групп/каналов).');
    process.exit(1);
  }

  console.log(`🔍 Поиск ментора "${mentorLoginOrId}" и валидация Chat ID "${rawChatId}"...`);

  const result = await bindMentorTelegramChatId(mentorLoginOrId, rawChatId);

  if (!result.ok) {
    console.error(`❌ Ошибка: ${result.error}`);
    process.exit(1);
  }

  console.log(`✅ Успешно! Ментору @${result.user?.login} (ID: ${result.user?.id}) привязан Telegram Chat ID: ${result.user?.telegramChatId}`);
  console.log('🎉 Теперь бот будет корректно направлять карточки сдачи ДЗ и интерактивные кнопки этому ментору.');
}

main()
  .catch((err) => {
    console.error('❌ Непредвиденная ошибка выполнения скрипта:', err);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
