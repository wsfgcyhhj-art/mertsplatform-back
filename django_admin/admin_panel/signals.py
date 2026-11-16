from django.db.models.signals import post_save
from django.dispatch import receiver
from admin_panel.models import Submission, SubmissionStatusChoices, ScoreAdjustment
from admin_panel.services.achievement_service import evaluate_user_achievements


@receiver(post_save, sender=Submission)
def on_submission_saved(sender, instance: Submission, created, **kwargs):
    """
    Auto-evaluates gamification rules when a mentor accepts homework.
    """
    if instance.status == SubmissionStatusChoices.ACCEPTED:
        try:
            evaluate_user_achievements(instance.user_id, trigger_filter='SUBMISSION_ACCEPTED')
        except Exception:
            pass


@receiver(post_save, sender=ScoreAdjustment)
def on_score_adjustment_saved(sender, instance: ScoreAdjustment, created, **kwargs):
    """
    Auto-evaluates TOTAL_SCORE achievements when points are added or removed.
    """
    try:
        evaluate_user_achievements(instance.user_id, trigger_filter='SCORE_ADJUSTED')
    except Exception:
        pass
