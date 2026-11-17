import logging
from django.db import transaction
from django.db.models.signals import pre_save, post_save
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
    if instance.pk:
        try:
            old = Submission.objects.get(pk=instance.pk)
            instance._old_status = old.status
            instance._old_score = old.score
            instance._old_comment = old.reviewer_comment
            instance._old_voice = old.voice_feedback_url
        except Submission.DoesNotExist:
            instance._old_status = None
            instance._old_score = None
            instance._old_comment = None
    else:
        instance._old_status = None
        instance._old_score = None
        instance._old_comment = None


@receiver(pre_save, sender=User)
def on_user_pre_save(sender, instance: User, **kwargs):
    """
    Captures prior current_month to detect promotion to the next stage.
    """
    if instance.pk:
        try:
            old = User.objects.get(pk=instance.pk)
            instance._old_current_month = old.current_month
        except User.DoesNotExist:
            instance._old_current_month = None
    else:
        instance._old_current_month = None


# --- Post-save Transactional Notification Handlers ---

@receiver(post_save, sender=Lesson)
def on_lesson_post_save(sender, instance: Lesson, created, **kwargs):
    """
    1) Auto-notifies target month students when a new video lesson is created.
    """
    if created:
        def _send():
            try:
                instance._telegram_delivery = notify_lesson_published(instance)
            except Exception as e:
                logger.warning("Error dispatching lesson notification: %s", e)

        transaction.on_commit(_send)


@receiver(post_save, sender=Task)
def on_task_post_save(sender, instance: Task, created, **kwargs):
    """
    2) Auto-notifies target month students when a new homework task is created.
    """
    if created:
        def _send():
            try:
                instance._telegram_delivery = notify_task_published(instance)
            except Exception as e:
                logger.warning("Error dispatching task notification: %s", e)

        transaction.on_commit(_send)


@receiver(post_save, sender=Submission)
def on_submission_post_save(sender, instance: Submission, created, **kwargs):
    """
    3) Evaluates gamification rules on ACCEPTED status and notifies student if review changed.
    """
    # Gamification trigger
    if instance.status == SubmissionStatusChoices.ACCEPTED:
        try:
            evaluate_user_achievements(instance.user_id, trigger_filter='SUBMISSION_ACCEPTED')
        except Exception as e:
            logger.warning("Error evaluating achievements on submission: %s", e)

    # Review notification: only if reviewed status AND review fields changed
    is_reviewed = instance.status in (
        SubmissionStatusChoices.ACCEPTED,
        SubmissionStatusChoices.REVISION,
        SubmissionStatusChoices.IN_REVIEW,
    )
    old_status = getattr(instance, '_old_status', None)
    old_score = getattr(instance, '_old_score', None)
    old_comment = getattr(instance, '_old_comment', None)

    changed = (
        instance.status != old_status
        or instance.score != old_score
        or instance.reviewer_comment != old_comment
        or instance.voice_feedback_url != getattr(instance, '_old_voice', None)
    )

    if is_reviewed and changed:
        def _send():
            try:
                notify_submission_reviewed(instance)
            except Exception as e:
                logger.warning("Error dispatching submission review notification: %s", e)

        transaction.on_commit(_send)


@receiver(post_save, sender=UserAchievement)
def on_user_achievement_post_save(sender, instance: UserAchievement, created, **kwargs):
    """
    4) Auto-notifies student when a new achievement is unlocked.
    """
    if created:
        def _send():
            try:
                notify_achievement_unlocked(instance.user_id, instance.achievement)
            except Exception as e:
                logger.warning("Error dispatching achievement notification: %s", e)

        transaction.on_commit(_send)


@receiver(post_save, sender=ScoreAdjustment)
def on_score_adjustment_post_save(sender, instance: ScoreAdjustment, created, **kwargs):
    """
    5) Auto-evaluates TOTAL_SCORE achievements and notifies student about score adjustment.
    """
    try:
        evaluate_user_achievements(instance.user_id, trigger_filter='SCORE_ADJUSTED')
    except Exception as e:
        logger.warning("Error evaluating achievements on score adjustment: %s", e)

    if created:
        def _send():
            try:
                notify_score_adjustment_granted(instance)
            except Exception as e:
                logger.warning("Error dispatching score adjustment notification: %s", e)

        transaction.on_commit(_send)


@receiver(post_save, sender=User)
def on_user_post_save(sender, instance: User, created, **kwargs):
    """
    6) Auto-notifies student when promoted to next study month.
    """
    if not created and instance.role == RoleChoices.STUDENT:
        old_month = getattr(instance, '_old_current_month', None)
        if old_month is not None and instance.current_month > old_month:
            new_month = instance.current_month

            def _send():
                try:
                    notify_month_advanced(instance, new_month)
                except Exception as e:
                    logger.warning("Error dispatching month advance notification: %s", e)

            transaction.on_commit(_send)
