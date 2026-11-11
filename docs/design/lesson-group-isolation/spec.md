# Feature Specification: Изоляция видеоуроков по учебным группам

## Requirements
- **FR-001**: Модель `Lesson` содержит поле `groupNumber` (`@map("group_number")`) и составной индекс `@@index([groupNumber, month, order])`.
- **FR-002**: Существующие уроки в БД заполняются актуальной группой студентов (или `"ALL"`), чтобы не нарушать целостность данных.
- **FR-003**: `GET /api/v1/lessons` возвращает уроки строго группы студента (`req.user.groupNumber`) с фильтрацией по месяцу и поддержкой просмотра пройденных месяцев (`month <= req.user.currentMonth`).
- **FR-004**: В админских эндпоинтах (`/api/v1/admin/lessons`), React-админке (`LessonsTab.jsx`) и Django Admin (`models.py`, `admin.py`) реализованы выбор существующих групп / ручной ввод `groupNumber` и фильтрация по группе.
- **FR-005**: В компоненте `LessonVideos.jsx` добавлен переключатель месяцев для повторения пройденного материала (`1 .. user.currentMonth`).
