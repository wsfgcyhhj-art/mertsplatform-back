import { PrismaClient, Role } from '@prisma/client';
import bcrypt from 'bcrypt';
import { DEFAULT_ACHIEVEMENTS, ensureDefaultAchievements } from '../src/services/achievements.js';

const prisma = new PrismaClient();

async function main() {
  console.log('🌱 Начинается сидирование базы данных Merts Platform...');

  // 1. Создание дефолтного администратора
  const adminLogin = 'admin';
  const adminPassword = 'adminPassword123';
  const passwordHash = await bcrypt.hash(adminPassword, 10);

  const admin = await prisma.user.upsert({
    where: { login: adminLogin },
    update: {
      role: Role.ADMIN,
    },
    create: {
      login: adminLogin,
      passwordHash,
      role: Role.ADMIN,
      name: 'Главный Администратор',
      telegram: '@admin',
      currentMonth: 1,
    },
  });

  console.log(`✅ Администратор готов:`);
  console.log(`   Логин:  ${admin.login}`);
  console.log(`   Пароль: ${adminPassword}`);
  console.log(`   Роль:   ${admin.role}`);

  // 2. Инициализация дефолтных ачивок без удаления кастомных ачивок администратора
  console.log(`🏆 Инициализация достижений (системных: ${DEFAULT_ACHIEVEMENTS.length})...`);
  await ensureDefaultAchievements();
  console.log(`✅ Системные достижения и правила синхронизированы.`);

  console.log('✨ Сидирование успешно завершено!');
}

main()
  .catch((e) => {
    console.error('❌ Ошибка при сидировании базы данных:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
