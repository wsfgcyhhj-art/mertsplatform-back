import logging
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from admin_panel.models import (
    User,
    Lesson,
    Task,
    Submission,
    SubmissionStatusChoices,
    ScoreAdjustment,
    UserAchievement,
    RoleChoices,
    PlatformSetting,
)
from admin_panel.services.achievement_service import evaluate_user_achievements
from admin_panel.services.telegram_service import (
    notify_lesson_published,
    notify_task_published,
    notify_submission_reviewed,
    notify_achievement_unlocked,
    notify_score_adjustment_granted,
    notify_month_advanced,
)

logger = logging.getLogger('signals')


# --- Pre-save State Trackers (Anti-Spam & Change Detection) ---

@receiver(pre_save, sender=Submission)
def on_submission_pre_save(sender, instance: Submission, **kwargs):
    """
    Captures prior state to prevent duplicate notifications if an unchanged submission is saved.
    """
    if instance._state.adding or not instance.pk:
        instance._old_status = None
        instance._old_score = None
        instance._old_comment = None
        instance._old_voice = None
        return
    try:
        old = Submission.objects.select_for_update().get(pk=instance.pk)
        instance._old_status = old.status
        instance._old_score = old.score
        instance._old_comment = old.reviewer_comment
        instance._old_voice = old.voice_feedback_url
        if old.status == SubmissionStatusChoices.REVISION or getattr(old, 'was_revised', False):
            instance.was_revised = True
    except Submission.DoesNotExist:
        instance._old_status = None
        instance._old_score = None
        instance._old_comment = None
        instance._old_voice = None


@receiver(pre_save, sender=User)
def on_user_pre_save(sender, instance: User, **kwargs):
    """
    Captures prior current_month to detect promotion to the next stage.
    """
    update_fields = kwargs.get('update_fields')
    if update_fields is not None and 'current_month' not in update_fields:
        instance._old_current_month = None
        return
    if instance._state.adding or not instance.pk:
        instance._old_current_month = None
        return
    try:
        old = User.objects.select_for_update().get(pk=instance.pk)
        instance._old_current_month = old.current_month
    except User.DoesNotExist:
        instance._old_current_month = None


# --- Post-save Transactional Notification Handlers ---

@receiver(post_save, sender=Lesson)
def on_lesson_post_save(sender, instance: Lesson, created, **kwargs):
    """
    1) Auto-notifies target month students when a new video lesson is created.
    """
    if created:
        instance._telegram_delivery = notify_lesson_published(instance)


@receiver(post_save, sender=Task)
def on_task_post_save(sender, instance: Task, created, **kwargs):
    """
    2) Auto-notifies target month students when a new homework task is created.
    """
    if created:
        instance._telegram_delivery = notify_task_published(instance)


@receiver(post_save, sender=Submission)
def on_submission_post_save(sender, instance: Submission, created, **kwargs):
    """
    3) Evaluates gamification rules on ACCEPTED status and notifies student if review changed.
    """
    # Gamification trigger
    if instance.status == SubmissionStatusChoices.ACCEPTED:
        evaluate_user_achievements(instance.user_id, trigger_filter='SUBMISSION_ACCEPTED')

    # Review notification: only if reviewed status AND review fields changed
    is_reviewed = instance.status in (
        SubmissionStatusChoices.ACCEPTED,
        SubmissionStatusChoices.REVISION,
        SubmissionStatusChoices.IN_REVIEW,
    )
    update_fields = kwargs.get('update_fields')
    changed = any(
        (update_fields is None or field in update_fields)
        and getattr(instance, field) != getattr(instance, previous, None)
        for field, previous in (
            ('status', '_old_status'),
            ('score', '_old_score'),
            ('reviewer_comment', '_old_comment'),
            ('voice_feedback_url', '_old_voice'),
        )
    )

    if is_reviewed and changed:
        notify_submission_reviewed(instance)


@receiver(post_save, sender=UserAchievement)
def on_user_achievement_post_save(sender, instance: UserAchievement, created, **kwargs):
    """
    4) Auto-notifies student when a new achievement is unlocked.
    """
    if created:
        notify_achievement_unlocked(instance.user_id, instance.achievement)


@receiver(post_save, sender=ScoreAdjustment)
def on_score_adjustment_post_save(sender, instance: ScoreAdjustment, created, **kwargs):
    """
    5) Auto-evaluates TOTAL_SCORE achievements and notifies student about score adjustment.
    """
    evaluate_user_achievements(instance.user_id, trigger_filter='SCORE_ADJUSTED')

    if created:
        notify_score_adjustment_granted(instance)


@receiver(post_save, sender=User)
def on_user_post_save(sender, instance: User, created, **kwargs):
    """
    6) Auto-notifies student when promoted to next study month.
    """
    if not created and instance.role == RoleChoices.STUDENT:
        old_month = getattr(instance, '_old_current_month', None)
        if old_month is not None and instance.current_month > old_month:
            new_month = instance.current_month

            notify_month_advanced(instance, new_month)


@receiver(post_save, sender=PlatformSetting)
@receiver(post_delete, sender=PlatformSetting)
def on_platform_setting_changed(sender, **kwargs):
    from admin_panel.services.settings_service import invalidate_settings_cache
    invalidate_settings_cache()
