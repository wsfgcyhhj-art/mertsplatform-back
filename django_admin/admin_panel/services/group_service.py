import re
import uuid
import logging
from typing import List, Tuple, Optional
from django.db import transaction

logger = logging.getLogger(__name__)


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
    """
    Scans existing User, Lesson, and Task records and ensures all unique group_numbers
    are recorded as StudyGroup entities in the database.
    """
    from admin_panel.models import User, Lesson, Task, StudyGroup

    try:
        user_groups = User.objects.exclude(group_number__isnull=True).exclude(group_number='').values_list('group_number', flat=True).distinct()
        lesson_groups = Lesson.objects.exclude(group_number__isnull=True).exclude(group_number='').values_list('group_number', flat=True).distinct()
        task_groups = Task.objects.exclude(group_number__isnull=True).exclude(group_number='').values_list('group_number', flat=True).distinct()

        all_names = set()
        for g in list(user_groups) + list(lesson_groups) + list(task_groups):
            if g and str(g).strip() and str(g).strip().upper() != 'ALL':
                all_names.add(str(g).strip())

        existing_names = set(StudyGroup.objects.values_list('name', flat=True))
        missing = all_names - existing_names

        for name in missing:
            month = parse_month_from_group_name(name)
            StudyGroup.objects.get_or_create(
                name=name,
                defaults={
                    'id': str(uuid.uuid4()),
                    'month': month,
                }
            )
    except Exception as e:
        logger.warning("Error syncing study groups: %s", e)


def get_study_group_choices(include_all: bool = True) -> List[Tuple[str, str]]:
    """
    Generates a list of (value, label) tuples for Django forms / admin Select dropdowns.
    Format: 'js-02 (Месяц 2 • 14 студентов)'
    """
    from admin_panel.models import StudyGroup, User, RoleChoices

    choices: List[Tuple[str, str]] = []
    if include_all:
        choices.append(('', '— Все группы месяца (общий доступ) —'))

    try:
        groups = StudyGroup.objects.all().order_by('month', 'name')
        for g in groups:
            st_count = User.objects.filter(role=RoleChoices.STUDENT, group_number=g.name).count()
            count_label = f"{st_count} студ." if st_count > 0 else "нет студентов"
            label = f"{g.name} — Месяц {g.month} ({count_label})"
            choices.append((g.name, label))
    except Exception:
        pass

    return choices
