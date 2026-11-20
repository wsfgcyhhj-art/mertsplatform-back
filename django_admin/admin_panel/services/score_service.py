from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from admin_panel.models import ScoreAdjustment, Submission, SubmissionStatusChoices


def latest_accepted(queryset):
    latest = Submission.objects.filter(
        user_id=OuterRef('user_id'),
        task_id=OuterRef('task_id'),
        status=SubmissionStatusChoices.ACCEPTED,
    ).order_by('-version', '-created_at', '-id')
    return queryset.filter(status=SubmissionStatusChoices.ACCEPTED, id=Subquery(latest.values('id')[:1]))


def annotate_user_scores(users_qs, month=None):
    latest_sub_id = Submission.objects.filter(
        user_id=OuterRef('user_id'),
        task_id=OuterRef('task_id'),
        status=SubmissionStatusChoices.ACCEPTED,
    ).order_by('-version', '-created_at', '-id').values('id')[:1]

    accepted_filter = Q(user_id=OuterRef('pk'), status=SubmissionStatusChoices.ACCEPTED, id=Subquery(latest_sub_id))
    sent_filter = Q(user_id=OuterRef('pk'))
    adj_filter = Q(user_id=OuterRef('pk'))
    if month is not None:
        accepted_filter &= Q(task__month=month)
        sent_filter &= Q(task__month=month)
        adj_filter &= Q(month=month)

    sub_score_sq = Subquery(
        Submission.objects.filter(accepted_filter)
        .values('user_id')
        .annotate(total=Coalesce(Sum('score'), 0))
        .values('total')[:1],
        output_field=IntegerField(),
    )
    accepted_cnt_sq = Subquery(
        Submission.objects.filter(accepted_filter)
        .values('user_id')
        .annotate(cnt=Count('id'))
        .values('cnt')[:1],
        output_field=IntegerField(),
    )
    sent_cnt_sq = Subquery(
        Submission.objects.filter(sent_filter)
        .values('user_id')
        .annotate(cnt=Count('id'))
        .values('cnt')[:1],
        output_field=IntegerField(),
    )
    adj_score_sq = Subquery(
        ScoreAdjustment.objects.filter(adj_filter)
        .values('user_id')
        .annotate(total=Coalesce(Sum('amount'), 0))
        .values('total')[:1],
        output_field=IntegerField(),
    )

    return users_qs.annotate(
        sub_score=Coalesce(sub_score_sq, Value(0)),
        adj_score=Coalesce(adj_score_sq, Value(0)),
        tasks_accepted_count=Coalesce(accepted_cnt_sq, Value(0)),
        tasks_sent_count=Coalesce(sent_cnt_sq, Value(0)),
    ).annotate(
        total_score=F('sub_score') + F('adj_score'),
    )
