# Implementation Plan: Изоляция видеоуроков по группам

1. `backend/prisma/schema.prisma` — поле `groupNumber String @default("1") @map("group_number")` и `@@index([groupNumber, month, order])` в `Lesson`.
2. Миграция БД через `npx prisma db execute` (с заполнением `group_number` существующих уроков активной группой из `User`) + `npx prisma generate`.
3. `django_admin/admin_panel/models.py` и `django_admin/admin_panel/admin.py` — поле `group_number`, кастомная форма с автоподсказкой (`datalist`) существующих групп, фильтр и колонка в списке.
4. `backend/src/routes/lessons.ts` и `backend/src/routes/adminLessons.ts` — фильтрация по `groupNumber` и `month <= req.user.currentMonth`, а также список доступных групп `availableGroups`.
5. `src/pages/LessonsPage/ui/LessonVideos.jsx` и `src/pages/AdminPage/ui/LessonsTab.jsx` — переключатель месяцев для студента и выбор/ввод группы в админке.
