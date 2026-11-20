import uuid
from django.db import models, transaction
from django.utils import timezone
from django.core.validators import RegexValidator

chat_id_validator = RegexValidator(
    regex=r'^-?\d+$',
    message='Chat ID должен состоять только из цифр (с возможным знаком минус для групп/каналов).'
)


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


class TriggerTypeChoices(models.TextChoices):
    MANUAL = 'MANUAL', 'Ручная выдача (MANUAL)'
    ON_REGISTER = 'ON_REGISTER', 'При регистрации / первом входе (ON_REGISTER)'
    TOTAL_SCORE = 'TOTAL_SCORE', 'Набрать X суммарных баллов (TOTAL_SCORE)'
    ACCEPTED_TASKS = 'ACCEPTED_TASKS', 'Сдать X принятых заданий (ACCEPTED_TASKS)'
    BONUS_TASKS = 'BONUS_TASKS', 'Сдать X бонусных заданий (BONUS_TASKS)'
    FIRST_TRY_ACCEPTED = 'FIRST_TRY_ACCEPTED', 'Сдать X заданий с 1-й попытки (FIRST_TRY_ACCEPTED)'
    PERFECT_SCORE = 'PERFECT_SCORE', 'Сдать X заданий на макс. балл (PERFECT_SCORE)'
    REVISION_ACCEPTED = 'REVISION_ACCEPTED', 'Сдать X заданий после доработки (REVISION_ACCEPTED)'
    STREAK_DAYS = 'STREAK_DAYS', 'Активность X дней подряд / стрик (STREAK_DAYS)'
    EASTER_EGG = 'EASTER_EGG', 'Секретная пасхалка (EASTER_EGG)'


class AchievementCategoryChoices(models.TextChoices):
    START = 'START', 'Старт (START)'
    TASKS = 'TASKS', 'Домашки (TASKS)'
    SCORES = 'SCORES', 'Баллы (SCORES)'
    SECRET = 'SECRET', 'Секретные (SECRET)'
    SPECIAL = 'SPECIAL', 'Особые (SPECIAL)'
    GENERAL = 'general', 'Общие (general)'


class AtomicModel(models.Model):
    class Meta:
        abstract = True

    @transaction.atomic
    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class User(AtomicModel):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    login = models.CharField('Логин', max_length=255, unique=True)
    password_hash = models.CharField('Хэш пароля', max_length=255)
    role = models.CharField('Роль', max_length=32, choices=RoleChoices.choices, default=RoleChoices.STUDENT)
    has_subscription = models.BooleanField(default=True, db_default=True)
    subscription_expires_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(default=False, db_default=False)
    password_uses_sha256 = models.BooleanField(default=False, db_default=False)
    name = models.CharField('Имя', max_length=255, blank=True, null=True)
    telegram = models.CharField('Telegram', max_length=255, blank=True, null=True)
    telegram_chat_id = models.CharField(
        'Telegram Chat ID',
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        validators=[chat_id_validator],
        help_text='Числовой Chat ID ментора в Telegram для получения карточек сдачи ДЗ',
    )
    telegram_auth_code = models.CharField('Telegram код привязки', max_length=255, unique=True, blank=True, null=True)
    telegram_username = models.CharField('Telegram Username', max_length=255, blank=True, null=True)
    group_number = models.CharField('Номер группы', max_length=64, blank=True, null=True)
    study_group = models.ForeignKey(
        'StudyGroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='group_id',
        related_name='students',
        verbose_name='Учебная группа',
    )
    current_month = models.IntegerField('Текущий месяц', default=1)
    avatar_url = models.TextField('URL аватара', blank=True, null=True)
    banner_url = models.TextField('URL баннера', blank=True, null=True)
    streak_count = models.IntegerField('Стрик (дней)', default=0)
    last_active_date = models.DateTimeField('Последняя активность', blank=True, null=True)
    mentor = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        db_column='mentor_id',
        limit_choices_to={'role': RoleChoices.ADMIN},
        verbose_name='Персональный ментор',
    )
    created_at = models.DateTimeField('Дата создания', default=timezone.now)
    updated_at = models.DateTimeField('Дата обновления', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'User'
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['-created_at']

    USERNAME_FIELD = 'login'
    REQUIRED_FIELDS = []

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_active(self):
        return True

    @property
    def is_staff(self):
        return self.role == RoleChoices.ADMIN

    @property
    def is_superuser(self):
        return self.role == RoleChoices.ADMIN

    def check_password(self, raw_password: str) -> bool:
        from django.contrib.auth.hashers import check_password
        import bcrypt, hashlib
        if not raw_password or len(raw_password) > 1024:
            return False
        if not self.password_hash.startswith(('$2a$', '$2b$', '$2y$')):
            return check_password(raw_password, self.password_hash)
        # Existing accounts include bcrypt(raw) and bcrypt(SHA256(raw)).
        candidates = [hashlib.sha256(raw_password.encode()).hexdigest().encode()]
        if not self.password_uses_sha256 and len(raw_password.encode()) <= 72:
            candidates.insert(0, raw_password.encode())
        try:
            return any(bcrypt.checkpw(candidate, self.password_hash.encode()) for candidate in candidates)
        except ValueError:
            return False

    def set_password(self, raw_password: str) -> None:
        from django.contrib.auth.hashers import make_password
        self.password_hash = make_password(raw_password)
        self.password_uses_sha256 = False

    def calculate_total_score(self) -> int:
        from django.db.models import Sum
        from admin_panel.services.score_service import latest_accepted
        sub_score = latest_accepted(self.submissions.all()).aggregate(s=Sum('score'))['s'] or 0
        adj_score = self.score_adjustments.aggregate(s=Sum('amount'))['s'] or 0
        return sub_score + adj_score

    def accepted_tasks_count(self) -> int:
        from admin_panel.services.score_service import latest_accepted
        return latest_accepted(self.submissions.all()).count()

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        if self.telegram_chat_id:
            self.telegram_chat_id = self.telegram_chat_id.strip() or None
        study_group = None
        if self.study_group_id:
            try:
                study_group = self.study_group
            except StudyGroup.DoesNotExist:
                self.study_group_id = None
        if study_group:
            self.group_number = study_group.name
        elif self.group_number:
            self.group_number = self.group_number.strip()
            self.study_group = StudyGroup.objects.filter(name=self.group_number).first()
        if self.group_number and (not self.current_month or self.current_month == 1):
            from admin_panel.services.group_service import parse_month_from_group_name
            extracted = parse_month_from_group_name(self.group_number)
            if extracted > 1:
                self.current_month = extracted
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name or self.login} (@{self.login})"


class Session(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sessions',
        db_column='user_id',
        verbose_name='Пользователь',
    )
    refresh_token = models.CharField('Refresh Token', max_length=512, unique=True, db_column='refresh_token')
    expires_at = models.DateTimeField('Срок действия', db_column='expires_at')
    created_at = models.DateTimeField('Дата создания', default=timezone.now, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'Session'
        verbose_name = 'Сессия пользователя'
        verbose_name_plural = 'Сессии пользователей'
        ordering = ['-created_at']

    def __str__(self):
        return f"Session for {self.user.login} ({self.id})"


class StudyGroup(models.Model):
    def clean(self):
        super().clean()
        if self.is_active:
            from admin_panel.services.group_service import validate_group_name
            self.name = validate_group_name(self.name)

    is_active = models.BooleanField(default=True, db_default=True)
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    name = models.CharField('Название группы', max_length=64, unique=True)
    month = models.IntegerField('Месяц обучения', default=1)
    created_at = models.DateTimeField('Дата создания', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'StudyGroup'
        verbose_name = 'Учебная группа'
        verbose_name_plural = 'Учебные группы'
        ordering = ['month', 'name']

    def __str__(self):
        return f"{self.name} (Месяц {self.month})"

    def save(self, *args, **kwargs):
        if not self.month or self.month == 1:
            from admin_panel.services.group_service import parse_month_from_group_name
            self.month = parse_month_from_group_name(self.name)
        super().save(*args, **kwargs)

    @property
    def students_count(self) -> int:
        return User.objects.filter(role=RoleChoices.STUDENT, group_number=self.name).count()

    @property
    def lessons_count(self) -> int:
        return Lesson.objects.filter(group_number=self.name).count()

    @property
    def tasks_count(self) -> int:
        return Task.objects.filter(group_number=self.name).count()


class Lesson(AtomicModel):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    title = models.CharField('Название урока', max_length=255)
    video_link = models.CharField('Ссылка на видео', max_length=500)
    youtube_id = models.CharField('YouTube ID', max_length=128, blank=True)
    group_number = models.CharField('Номер группы', max_length=64, default='1')
    month = models.IntegerField('Месяц', default=1)
    order = models.IntegerField('Порядок', default=1)
    created_at = models.DateTimeField('Дата создания', default=timezone.now)
    updated_at = models.DateTimeField('Дата обновления', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'Lesson'
        verbose_name = 'Видеоурок'
        verbose_name_plural = 'Видеоуроки'
        ordering = ['group_number', 'month', 'order']

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[Группа {self.group_number} | Месяц {self.month} | #{self.order}] {self.title}"


class Task(AtomicModel):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    title = models.CharField('Название задания', max_length=255)
    description = models.TextField('Описание задания')
    topic = models.CharField('Тема (стек)', max_length=128)
    group_number = models.CharField(
        'Целевая группа',
        max_length=64,
        blank=True,
        null=True,
        help_text='Оставьте пустым (или укажите ALL) для всех групп месяца или выберите конкретную группу',
    )
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
        verbose_name_plural = 'Учебные задания'
        ordering = ['month', 'order']

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[Месяц {self.month}] {self.title} ({self.topic})"


class Submission(AtomicModel):
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
    mentor_telegram_msg_id = models.CharField('ID сообщения ментора в TG', max_length=255, blank=True, null=True)
    voice_feedback_url = models.CharField('Голосовой фидбек (file_id / URL)', max_length=500, blank=True, null=True)
    reviewed_at = models.DateTimeField('Дата проверки', blank=True, null=True)
    created_at = models.DateTimeField('Дата отправки', default=timezone.now)
    updated_at = models.DateTimeField('Дата обновления', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'Submission'
        constraints = [models.UniqueConstraint(fields=['user', 'task', 'version'], name='submission_attempt_unique')]
        verbose_name = 'Сдача ДЗ'
        verbose_name_plural = 'Проверка ДЗ'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} — {self.task} (v{self.version}, {self.status})"


class ScoreAdjustment(AtomicModel):
    idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
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
        verbose_name_plural = 'Бонусы и штрафы'
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.user}: {sign}{self.amount} баллов ({self.reason})"


class Achievement(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    code = models.CharField('Код ачивки', max_length=128, unique=True)
    title = models.CharField('Название', max_length=255)
    description = models.TextField('Описание')
    icon_url = models.TextField(
        'Иконка (URL / Data URI)',
        default='/api/v1/media/presets/icons/trophy.svg',
    )
    category = models.CharField(
        'Категория',
        max_length=128,
        choices=AchievementCategoryChoices.choices,
        default=AchievementCategoryChoices.TASKS,
    )
    trigger_type = models.CharField(
        'Тип триггера (правило)',
        max_length=64,
        choices=TriggerTypeChoices.choices,
        default=TriggerTypeChoices.MANUAL,
    )
    threshold = models.IntegerField(
        'Порог срабатывания (X)',
        blank=True,
        null=True,
        help_text='Числовое значение для триггеров баллов и заданий (например: 100 для баллов или 5 для ДЗ). Для MANUAL / ON_REGISTER / EASTER_EGG оставьте пустым.',
    )
    points = models.IntegerField('Очки за ачивку (+pts)', default=10)
    criteria = models.TextField('Критерий получения (текст для студента)', blank=True, null=True)
    is_active = models.BooleanField('Активна', default=True)
    created_at = models.DateTimeField('Дата создания', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'Achievement'
        verbose_name = 'Достижение (Ачивка)'
        verbose_name_plural = 'Каталог ачивок'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.title} ({self.code})"


class UserAchievement(AtomicModel):
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


class MediaAsset(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    kind = models.CharField('Тип медиа (AVATAR / BANNER / ICON)', max_length=64, default='GENERAL')
    mime_type = models.CharField('MIME-тип', max_length=128)
    data = models.BinaryField('Бинарные данные (WebP / SVG)')
    size_bytes = models.IntegerField('Размер (байт)')
    owner_id = models.CharField('ID владельца (User ID)', max_length=64, blank=True, null=True)
    created_at = models.DateTimeField('Дата загрузки', default=timezone.now)

    class Meta:
        managed = False
        db_table = 'MediaAsset'
        verbose_name = 'Медиа-ассет (БД Neon)'
        verbose_name_plural = 'Медиа-ассеты (БД Neon)'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.kind}] {self.id} ({self.mime_type}, {self.size_bytes} bytes)"


class SubscriptionGrant(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    telegram_username = models.CharField(max_length=32, unique=True)
    telegram_user_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    user = models.OneToOneField(User, on_delete=models.PROTECT, null=True, blank=True)
    group = models.ForeignKey(StudyGroup, on_delete=models.PROTECT)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    granted_by = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = 'SubscriptionGrant'
        verbose_name = 'Доступ к платформе'
        verbose_name_plural = 'Доступ к платформе'

    def __str__(self):
        return '@' + self.telegram_username


class TelegramIdentity(models.Model):
    telegram_user_id = models.CharField(primary_key=True, max_length=64)
    username = models.CharField(max_length=32, unique=True, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'TelegramIdentity'


class PasswordResetTicket(models.Model):
    token_hash = models.CharField(primary_key=True, max_length=64)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'PasswordResetTicket'


class AuthRateBucket(models.Model):
    key = models.CharField(primary_key=True, max_length=64)
    started_at = models.DateTimeField(default=timezone.now)
    attempts = models.IntegerField(default=0)
    class Meta:
        managed = False
        db_table = 'AuthRateBucket'


class TelegramUpdate(models.Model):
    update_id = models.BigIntegerField(primary_key=True)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        managed = False
        db_table = 'TelegramUpdate'


class TelegramOutbox(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid)
    dedupe_key = models.CharField(max_length=128, unique=True)
    chat_id = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default='pending', db_index=True)
    attempts = models.IntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        managed = False
        db_table = 'TelegramOutbox'


class ShopProduct(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    title = models.CharField('Название', max_length=255, unique=True)
    description = models.TextField('Описание', blank=True)
    price_som = models.PositiveIntegerField('Цена в сомах')
    price_coins = models.PositiveIntegerField('Цена в баллах')
    image_url = models.CharField('URL изображения', max_length=500, blank=True)
    stock = models.PositiveIntegerField('Остаток', default=0)
    is_active = models.BooleanField('Активен', default=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        managed = False
        db_table = 'ShopProduct'
        verbose_name = 'Товар магазина мерча'
        verbose_name_plural = 'Магазин мерча (Товары)'
        ordering = ('order', 'title')

    def __str__(self):
        return self.title


class ShopOrderStatus(models.TextChoices):
    PENDING = 'PENDING', 'Ожидает'
    COMPLETED = 'COMPLETED', 'Выдан'
    CANCELLED = 'CANCELLED', 'Отменён'


class ShopOrder(models.Model):

    id = models.CharField(primary_key=True, max_length=64, default=generate_uuid, editable=False)
    user = models.ForeignKey(User, models.PROTECT, related_name='shop_orders', verbose_name='Студент')
    product = models.ForeignKey(ShopProduct, models.PROTECT, verbose_name='Товар')
    price_coins = models.PositiveIntegerField('Списано баллов')
    status = models.CharField('Статус', max_length=16, choices=ShopOrderStatus.choices, default=ShopOrderStatus.PENDING)
    comment = models.CharField('Комментарий', max_length=500, blank=True)
    created_at = models.DateTimeField('Дата заказа', default=timezone.now)
    processed_by = models.CharField('Обработал', max_length=150, blank=True)
    processed_at = models.DateTimeField('Дата обработки', null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'ShopOrder'
        verbose_name = 'Заказ мерча'
        verbose_name_plural = 'Заказы мерча'
        ordering = ('-created_at', '-id')
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=ShopOrderStatus.values),
                                   name='shop_order_valid_status'),
        ]
