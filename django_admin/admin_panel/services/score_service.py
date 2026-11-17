from django.db.models import OuterRef, Subquery
from admin_panel.models import Submission


def latest_accepted(queryset):
    latest = Submission.objects.filter(user_id=OuterRef('user_id'), task_id=OuterRef('task_id'), status='ACCEPTED').order_by('-version', '-created_at', '-id')
    return queryset.filter(status='ACCEPTED', id=Subquery(latest.values('id')[:1]))
