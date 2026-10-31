import uuid
from django.db import models
from django.utils import timezone


def generate_uuid() -> str:
    return str(uuid.uuid4())


class RoleChoices(models.TextChoices):
    STUDENT = 'STUDENT', 'Студент (STUDENT)'
    ADMIN = 'ADMIN', 'Администратор (ADMIN)'


class SubmissionStatusChoices(models.TextChoices):
    SENT = 'SENT', 'Отправлено (SENT)'
    IN_REVIEW = 'IN_REVIEW', 'На проверке (IN_REVIEW)'
    REVISION = 'REVISION', 'На доработке (REVISION)'
    ACCEPTED = 'ACCEPTED', 'Принято (ACCEPTED)'


class User(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    login = models.CharField('Логин', max_length=255, unique=True)
    password_hash = models.CharField('Хэш пароля (bcrypt)', max_length=255)
    role = models.CharField('Роль', max_length=32, choices=RoleChoices.choices, default=RoleChoices.STUDENT)
    name = models.CharField('Имя', max_length=255, blank=True, null=True)
    telegram = models.CharField('Telegram', max_length=255, blank=True, null=True)
    group_number = models.CharField('Номер группы', max_length=64, blank=True, null=True)
    group_id = models.CharField('ID группы', max_length=64, blank=True, null=True)
    current_month = models.IntegerField('Текущий месяц', default=1)
    avatar_url = models.TextField('URL аватара', blank=True, null=True)
    banner_url = models.TextField('URL баннера', blank=True, null=True)
    created_at = models.DateTimeField('Дата создания', default=timezone.now)
    updated_at = models.DateTimeField('Дата обновления', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'User'
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name or self.login} (@{self.login})"


class Lesson(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    title = models.CharField('Название урока', max_length=255)
    video_link = models.CharField('Ссылка на видео', max_length=500)
    youtube_id = models.CharField('YouTube ID', max_length=128, blank=True)
    month = models.IntegerField('Месяц', default=1)
    order = models.IntegerField('Порядок', default=1)
    created_at = models.DateTimeField('Дата создания', default=timezone.now)
    updated_at = models.DateTimeField('Дата обновления', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'Lesson'
        verbose_name = 'Видеоурок'
        verbose_name_plural = 'Видеоуроки'
        ordering = ['month', 'order']

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[Месяц {self.month} | #{self.order}] {self.title}"


class Task(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    title = models.CharField('Название задания', max_length=255)
    description = models.TextField('Описание задания')
    topic = models.CharField('Тема (стек)', max_length=128)
    month = models.IntegerField('Месяц', default=1)
    order = models.IntegerField('Порядок', default=1)
    example_link = models.CharField('Ссылка на пример', max_length=500, blank=True, null=True)
    attachment_link = models.CharField('Ссылка на материалы', max_length=500, blank=True, null=True)
    has_score = models.BooleanField('Оценивается баллами', default=True)
    max_score = models.IntegerField('Макс. балл', default=10, blank=True, null=True)
    is_bonus = models.BooleanField('Бонусное задание', default=False)
    created_at = models.DateTimeField('Дата создания', default=timezone.now)
    updated_at = models.DateTimeField('Дата обновления', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'Task'
        verbose_name = 'Задание'
        verbose_name_plural = 'Задания'
        ordering = ['month', 'order']

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[Месяц {self.month}] {self.title} ({self.topic})"


class Submission(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    user = models.ForeignKey(User, models.DO_NOTHING, db_column='user_id', related_name='submissions', verbose_name='Студент')
    task = models.ForeignKey(Task, models.DO_NOTHING, db_column='task_id', related_name='submissions', verbose_name='Задание')
    reviewer = models.ForeignKey(
        User,
        models.SET_NULL,
        db_column='reviewer_id',
        related_name='reviewed_submissions',
        blank=True,
        null=True,
        verbose_name='Проверяющий'
    )
    version = models.IntegerField('Попытка (версия)', default=1)
    comment = models.TextField('Комментарий студента', blank=True, null=True)
    solution_link = models.CharField('Ссылка на GitHub', max_length=500)
    status = models.CharField('Статус', max_length=32, choices=SubmissionStatusChoices.choices, default=SubmissionStatusChoices.SENT)
    score = models.IntegerField('Баллы', blank=True, null=True)
    reviewer_comment = models.TextField('Комментарий ревьюера', blank=True, null=True)
    reviewed_at = models.DateTimeField('Дата проверки', blank=True, null=True)
    created_at = models.DateTimeField('Дата отправки', default=timezone.now)
    updated_at = models.DateTimeField('Дата обновления', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'Submission'
        verbose_name = 'Сдача ДЗ'
        verbose_name_plural = 'Сдачи ДЗ'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} — {self.task} (v{self.version}, {self.status})"


class ScoreAdjustment(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    user = models.ForeignKey(User, models.DO_NOTHING, db_column='user_id', related_name='score_adjustments', verbose_name='Студент')
    admin = models.ForeignKey(User, models.DO_NOTHING, db_column='admin_id', related_name='given_adjustments', verbose_name='Администратор')
    amount = models.IntegerField('Изменение баллов (+/-)')
    reason = models.TextField('Причина')
    month = models.IntegerField('Месяц', default=1)
    created_at = models.DateTimeField('Дата начисления', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'ScoreAdjustment'
        verbose_name = 'Корректировка баллов'
        verbose_name_plural = 'Корректировки баллов'
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.user}: {sign}{self.amount} баллов ({self.reason})"


class Achievement(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    code = models.CharField('Код ачивки', max_length=128, unique=True)
    title = models.CharField('Название', max_length=255)
    description = models.TextField('Описание')
    icon_url = models.CharField('Иконка / Эмодзи', max_length=255)
    category = models.CharField('Категория', max_length=128, default='general')
    created_at = models.DateTimeField('Дата создания', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'Achievement'
        verbose_name = 'Достижение (Ачивка)'
        verbose_name_plural = 'Достижения (Ачивки)'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.icon_url} {self.title} ({self.code})"


class UserAchievement(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    user = models.ForeignKey(User, models.DO_NOTHING, db_column='user_id', related_name='user_achievements', verbose_name='Студент')
    achievement = models.ForeignKey(Achievement, models.DO_NOTHING, db_column='achievement_id', related_name='user_achievements', verbose_name='Достижение')
    awarded_at = models.DateTimeField('Дата награждения', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'UserAchievement'
        unique_together = (('user', 'achievement'),)
        verbose_name = 'Выданная ачивка'
        verbose_name_plural = 'Выданные ачивки'
        ordering = ['-awarded_at']

    def __str__(self):
        return f"{self.user} -> {self.achievement}"


class MonthlyScoreArchive(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    user = models.ForeignKey(User, models.DO_NOTHING, db_column='user_id', related_name='monthly_archives', verbose_name='Студент')
    month = models.IntegerField('Месяц')
    final_score = models.IntegerField('Итоговый балл')
    tasks_accepted_count = models.IntegerField('Принято задач')
    final_rank = models.IntegerField('Итоговое место')
    archived_at = models.DateTimeField('Дата архивации', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'MonthlyScoreArchive'
        unique_together = (('user', 'month'),)
        verbose_name = 'Архив рейтинга месяца'
        verbose_name_plural = 'Архивы рейтинга по месяцам'
        ordering = ['-month', 'final_rank']

    def __str__(self):
        return f"Месяц {self.month} | #{self.final_rank} {self.user} ({self.final_score} pts)"
