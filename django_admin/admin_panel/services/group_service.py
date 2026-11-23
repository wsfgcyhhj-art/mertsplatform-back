import re
import uuid
import logging
from typing import List, Tuple, Optional
from django.db import transaction
from django.db.models import Value
from django.db.models.functions import Lower, Replace

logger = logging.getLogger(__name__)


def normalize_group_number(group_number):
    return (group_number or '').replace(' ', '').lower()


def with_normalized_group(queryset):
    return queryset.alias(normalized_group=Lower(Replace('group_number', Value(' '), Value(''))))


def parse_month_from_group_name(group_name: Optional[str]) -> int:
    """
    Extracts numerical study month from group name (e.g. 'js-02' -> 2, 'md-03' -> 3, '02' -> 2).
    Defaults to 1 if no digits are present or if value is out of range [1, 24].
    """
    if not group_name or not str(group_name).strip():
        return 1

    clean = str(group_name).strip()
    match = re.search(r'(?:^|[^\d])(\d+)(?:[^\d]|$)', clean)
    if match:
        try:
            val = int(match.group(1))
            if 1 <= val <= 24:
                return val
        except (ValueError, TypeError):
            pass

    return 1


def ensure_study_groups_synced() -> None:
    """Compatibility no-op kept for legacy callers."""
    return None


def get_study_group_choices(include_all: bool = True) -> List[Tuple[str, str]]:
    """
    Generates a list of (value, label) tuples for Django forms / admin Select dropdowns.
    Format: 'js-02 (Месяц 2 • 14 студентов)'
    """
    from django.db.models import Count
    from admin_panel.models import StudyGroup, User, RoleChoices

    choices: List[Tuple[str, str]] = []
    if include_all:
        choices.append(('', '— Все группы месяца (общий доступ) —'))

    try:
        groups = list(StudyGroup.objects.filter(is_active=True).order_by('month', 'name'))
        counts = dict(
            User.objects.filter(role=RoleChoices.STUDENT, group_number__in=[g.name for g in groups])
            .values('group_number')
            .annotate(cnt=Count('id'))
            .values_list('group_number', 'cnt')
        )
        for g in groups:
            st_count = counts.get(g.name, 0)
            count_label = f"{st_count} студ." if st_count > 0 else "нет студентов"
            label = f"{g.name} — Месяц {g.month} ({count_label})"
            choices.append((g.name, label))
    except Exception:
        pass

    return choices


def validate_group_name(name):
    from django.core.exceptions import ValidationError
    name = str(name or '').strip().lower()
    if not re.fullmatch(r'[a-z]{2,12}-[0-9]{2}', name) or not 1 <= int(name.rsplit('-', 1)[1]) <= 24:
        raise ValidationError('Формат группы: js-02 (месяц 01–24).')
    return name
