from typing import Optional, List, Dict, Any
from django.db.models import Sum
from django.utils import timezone
from admin_panel.models import (
    User,
    Achievement,
    UserAchievement,
    Submission,
    SubmissionStatusChoices,
    ScoreAdjustment,
    TriggerTypeChoices,
)

DEFAULT_ACHIEVEMENTS_DATA = [
    {
        'code': 'WELCOME',
        'title': 'Начало пути',
        'description': 'Добро пожаловать на платформу! Первый шаг в мир разработки сделан.',
        'icon_url': '/api/v1/media/presets/icons/sparkles.svg',
        'category': 'general',
        'trigger_type': TriggerTypeChoices.ON_REGISTER,
        'threshold': 1,
        'points': 10,
        'criteria': 'Выдается сразу при успешной регистрации студента на платформе',
    },
    {
        'code': 'FIRST_STEP',
        'title': 'Первый рубеж',
        'description': 'Ваша первая практическая работа успешно проверена и принята ментором!',
        'icon_url': '/api/v1/media/presets/icons/check-circle.svg',
        'category': 'tasks',
        'trigger_type': TriggerTypeChoices.ACCEPTED_TASKS,
        'threshold': 1,
        'points': 15,
        'criteria': 'Принято минимум 1 учебное задание',
    },
    {
        'code': 'SCORE_20',
        'title': 'Первая двадцатка',
        'description': 'Набрано первые 20 баллов в общем рейтинге успеваемости.',
        'icon_url': '/api/v1/media/presets/icons/star.svg',
        'category': 'points',
        'trigger_type': TriggerTypeChoices.TOTAL_SCORE,
        'threshold': 20,
        'points': 20,
        'criteria': 'Суммарный рейтинг студента достигает 20 баллов',
    },
    {
        'code': 'SCORE_50',
        'title': 'Полпути к вершине',
        'description': 'Вы набрали 50 баллов! Отличный темп и превосходная дисциплина.',
        'icon_url': '/api/v1/media/presets/icons/trophy.svg',
        'category': 'points',
        'trigger_type': TriggerTypeChoices.TOTAL_SCORE,
        'threshold': 50,
        'points': 30,
        'criteria': 'Суммарный рейтинг студента достигает 50 баллов',
    },
    {
        'code': 'EASTER_EGG',
        'title': 'Любопытный исследователь',
        'description': 'Секретная пасхалка найдена! Настоящий инженер всегда изучает детали.',
        'icon_url': '/api/v1/media/presets/icons/search.svg',
        'category': 'special',
        'trigger_type': TriggerTypeChoices.EASTER_EGG,
        'threshold': 1,
        'points': 25,
        'criteria': 'Активация секретного терминала или клик по логотипу',
    },
    {
        'code': 'TOP_STUDENT_MONTH',
        'title': 'Лидер месяца',
        'description': 'Первое место в общем зачете месяца! Невероятный результат.',
        'icon_url': '/api/v1/media/presets/icons/crown.svg',
        'category': 'special',
        'trigger_type': TriggerTypeChoices.MANUAL,
        'threshold': None,
        'points': 50,
        'criteria': 'Вручную присуждается ментором за победу в месячном рейтинге',
    },
    {
        'code': 'PERFECT_SCORE',
        'title': 'Перфекционист',
        'description': 'Задание выполнено идеально с максимальным возможным баллом!',
        'icon_url': '/api/v1/media/presets/icons/zap.svg',
        'category': 'tasks',
        'trigger_type': TriggerTypeChoices.PERFECT_SCORE,
        'threshold': 1,
        'points': 20,
        'criteria': 'Получен максимальный балл хотя бы за одно задание с балльной системой',
    },
    {
        'code': 'BONUS_HUNTER',
        'title': 'Охотник за бонусами',
        'description': 'Выполнено со звездочкой: первое бонусное задание сдано на отлично.',
        'icon_url': '/api/v1/media/presets/icons/flame.svg',
        'category': 'tasks',
        'trigger_type': TriggerTypeChoices.BONUS_TASKS,
        'threshold': 1,
        'points': 25,
        'criteria': 'Принято хотя бы одно усложненное (бонусное) задание',
    },
    {
        'code': 'STREAK_MASTER',
        'title': 'Железная воля',
        'description': 'Непрерывный ежедневный стрик активности в течение 7 дней подряд!',
        'icon_url': '/api/v1/media/presets/icons/calendar.svg',
        'category': 'streak',
        'trigger_type': TriggerTypeChoices.STREAK_DAYS,
        'threshold': 7,
        'points': 35,
        'criteria': 'Стрик ежедневной учебной активности достигает 7 дней',
    },
    {
        'code': 'BUG_HUNTER',
        'title': 'Работа над ошибками',
        'description': 'Задание отправлено на доработку и после правок успешно принято ментором.',
        'icon_url': '/api/v1/media/presets/icons/code.svg',
        'category': 'tasks',
        'trigger_type': TriggerTypeChoices.REVISION_ACCEPTED,
        'threshold': 1,
        'points': 15,
        'criteria': 'Успешная сдача задания после статуса REVISION',
    },
    {
        'code': 'SPEED_DEMON',
        'title': 'Без лишних слов',
        'description': '3 разных задания приняты ментором с первой попытки (v1).',
        'icon_url': '/api/v1/media/presets/icons/rocket.svg',
        'category': 'tasks',
        'trigger_type': TriggerTypeChoices.FIRST_TRY_ACCEPTED,
        'threshold': 3,
        'points': 30,
        'criteria': '3 задания приняты с первой версии без доработок',
    },
    {
        'code': 'MONTH_FINISHER',
        'title': 'Прорыв месяца',
        'description': 'Успешно закрыты все 10 обязательных заданий учебного месяца!',
        'icon_url': '/api/v1/media/presets/icons/target.svg',
        'category': 'tasks',
        'trigger_type': TriggerTypeChoices.ACCEPTED_TASKS,
        'threshold': 10,
        'points': 50,
        'criteria': 'Принято 10 учебных заданий',
    },
]


def ensure_default_achievements():
    """
    Ensures standard gamification achievements exist in database.
    """
    for data in DEFAULT_ACHIEVEMENTS_DATA:
        code = data['code']
        Achievement.objects.get_or_create(
            code=code,
            defaults={
                'title': data['title'],
                'description': data['description'],
                'icon_url': data['icon_url'],
                'category': data['category'],
                'trigger_type': data['trigger_type'],
                'threshold': data['threshold'],
                'points': data['points'],
                'criteria': data['criteria'],
                'is_active': True,
            }
        )


def award_achievement(user_id: str, code: str) -> Optional[Dict[str, Any]]:
    """
    Awards an achievement to user by unique code. Prevents double-awarding.
    """
    normalized_code = code.strip().upper()
    try:
        ach = Achievement.objects.get(code=normalized_code)
    except Achievement.DoesNotExist:
        ensure_default_achievements()
        try:
            ach = Achievement.objects.get(code=normalized_code)
        except Achievement.DoesNotExist:
            return None

    if not ach.is_active:
        return None

    user_ach, created = UserAchievement.objects.get_or_create(
        user_id=user_id,
        achievement_id=ach.id,
        defaults={'awarded_at': timezone.now()}
    )

    if not created:
        return None

    # Try sending telegram notification if user linked their telegram
    try:
        from admin_panel.services.telegram_service import notify_achievement_unlocked
        notify_achievement_unlocked(user_id, ach)
    except Exception:
        pass

    return {
        'id': ach.id,
        'code': ach.code,
        'title': ach.title,
        'description': ach.description,
        'iconUrl': ach.icon_url,
        'category': ach.category,
        'triggerType': ach.trigger_type,
        'threshold': ach.threshold,
        'points': ach.points,
        'criteria': ach.criteria,
        'awardedAt': user_ach.awarded_at,
    }


def evaluate_user_achievements(user_id: str, trigger_filter: str = 'ALL') -> List[Dict[str, Any]]:
    """
    Evaluates 10 gamification triggers:
    MANUAL, ON_REGISTER, TOTAL_SCORE, ACCEPTED_TASKS, BONUS_TASKS,
    FIRST_TRY_ACCEPTED, PERFECT_SCORE, REVISION_ACCEPTED, STREAK_DAYS, EASTER_EGG.
    """
    active_achievements = list(Achievement.objects.filter(is_active=True).order_by('created_at'))
    if not active_achievements:
        ensure_default_achievements()
        active_achievements = list(Achievement.objects.filter(is_active=True).order_by('created_at'))

    unlocked_ids = set(UserAchievement.objects.filter(user_id=user_id).values_list('achievement_id', flat=True))
    candidates = [a for a in active_achievements if a.id not in unlocked_ids and a.trigger_type != TriggerTypeChoices.MANUAL]

    if not candidates:
        return []

    awarded: List[Dict[str, Any]] = []

    # 1. Instant Event Triggers
    if trigger_filter in (TriggerTypeChoices.ON_REGISTER, TriggerTypeChoices.EASTER_EGG):
        for ach in candidates:
            if ach.trigger_type == trigger_filter:
                res = award_achievement(user_id, ach.code)
                if res:
                    awarded.append(res)
        return awarded

    # 2. Metric-Based Dynamic Triggers
    all_submissions = list(
        Submission.objects.filter(user_id=user_id)
        .select_related('task')
        .order_by('version')
    )
    user = User.objects.filter(id=user_id).first()
    current_streak = user.streak_count if user else 0

    adj_sum = ScoreAdjustment.objects.filter(user_id=user_id).aggregate(s=Sum('amount'))['s'] or 0
    accepted_subs = [s for s in all_submissions if s.status == SubmissionStatusChoices.ACCEPTED]
    sub_score = sum((s.score or 0) for s in accepted_subs)
    total_score = sub_score + adj_sum

    # Group by task
    subs_by_task: Dict[str, List[Submission]] = {}
    for sub in all_submissions:
        subs_by_task.setdefault(sub.task_id, []).append(sub)

    accepted_task_ids = set()
    bonus_accepted_task_ids = set()
    first_try_accepted_task_ids = set()
    perfect_score_task_ids = set()
    revision_accepted_task_ids = set()

    for task_id, task_subs in subs_by_task.items():
        accepted_for_task = [s for s in task_subs if s.status == SubmissionStatusChoices.ACCEPTED]
        if not accepted_for_task:
            continue

        accepted_task_ids.add(task_id)
        task_meta = accepted_for_task[0].task

        if task_meta and task_meta.is_bonus:
            bonus_accepted_task_ids.add(task_id)

        had_revision = any(s.status == SubmissionStatusChoices.REVISION for s in task_subs)
        accepted_on_v1 = any(s.version == 1 for s in accepted_for_task)
        if accepted_on_v1 and not had_revision:
            first_try_accepted_task_ids.add(task_id)

        if had_revision:
            revision_accepted_task_ids.add(task_id)

        if task_meta and task_meta.has_score and task_meta.max_score:
            if any(s.score is not None and s.score >= task_meta.max_score for s in accepted_for_task):
                perfect_score_task_ids.add(task_id)

    for ach in candidates:
        threshold = ach.threshold if ach.threshold is not None else 1
        should_award = False

        if ach.trigger_type == TriggerTypeChoices.TOTAL_SCORE:
            should_award = total_score >= threshold
        elif ach.trigger_type == TriggerTypeChoices.ACCEPTED_TASKS:
            should_award = len(accepted_task_ids) >= threshold
        elif ach.trigger_type == TriggerTypeChoices.BONUS_TASKS:
            should_award = len(bonus_accepted_task_ids) >= threshold
        elif ach.trigger_type == TriggerTypeChoices.FIRST_TRY_ACCEPTED:
            should_award = len(first_try_accepted_task_ids) >= threshold
        elif ach.trigger_type == TriggerTypeChoices.PERFECT_SCORE:
            should_award = len(perfect_score_task_ids) >= threshold
        elif ach.trigger_type == TriggerTypeChoices.REVISION_ACCEPTED:
            should_award = len(revision_accepted_task_ids) >= threshold
        elif ach.trigger_type == TriggerTypeChoices.STREAK_DAYS:
            should_award = current_streak >= threshold

        if should_award:
            res = award_achievement(user_id, ach.code)
            if res:
                awarded.append(res)

    return awarded
