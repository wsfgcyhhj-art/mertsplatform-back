import base64
import logging
import os
from urllib.parse import quote

import httpx
from django.utils import timezone

from admin_panel.models import Submission
from admin_panel.services.github_service import GitHubValidationError, get_github_headers, parse_github_repo_url

logger = logging.getLogger('telegram_service')

ALLOWED_EXTENSIONS = ('.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css')
IGNORED_DIRS = frozenset({
    'node_modules', 'venv', '.venv', 'env', '__pycache__', '.git',
    'dist', 'build', '.next', 'coverage', 'staticfiles', 'vendor',
    'migrations', '.idea', '.vscode', 'assets', 'images', 'img', 'public',
})
IGNORED_FILES = frozenset({
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock',
    'pipfile.lock', 'uv.lock', 'cargo.lock', 'composer.lock', 'bun.lockb',
})
PRIORITY_STEMS = (
    'main', 'app', 'index', 'server', 'views', 'models', 'services',
    'routes', 'urls', 'api', 'manage', 'script', 'component',
)
MAX_FILES = 6
MAX_TOTAL_CHARS = 12_000
MAX_FEEDBACK_CHARS = 600

SYSTEM_PROMPT = (
    "Ты строгий, но дружелюбный AI-код-ревьюер образовательной платформы MertsPlatform.\n"
    "Проверь код студента по заданию строго по 3 пунктам:\n"
    "1) Безопасность: хардкод токенов, паролей, API-ключей или секретов.\n"
    "2) Соответствие ТЗ: выполнены ли базовые требования задания.\n"
    "3) Код и баги: грубые синтаксические или логические ошибки.\n"
    "Ответь структурированно на русском языке, строго до 550 символов (3 коротких пункта + итог)."
)


def _is_candidate_source_path(path: str) -> bool:
    if not path or not isinstance(path, str):
        return False
    norm = path.strip('/')
    parts = [p.lower() for p in norm.split('/') if p]
    if not parts:
        return False
    if any(part in IGNORED_DIRS for part in parts[:-1]):
        return False
    filename = parts[-1]
    if filename in IGNORED_FILES or filename.endswith(('.min.js', '.min.css', '.d.ts', '.map', '.lock')):
        return False
    return filename.endswith(ALLOWED_EXTENSIONS)


def _score_source_path(path: str) -> tuple[int, int, str]:
    parts = path.strip('/').split('/')
    filename = parts[-1].lower()
    stem = filename.rsplit('.', 1)[0]
    is_test = 'test' in stem or 'spec' in stem
    priority = 0 if any(stem == p or stem.startswith(p) for p in PRIORITY_STEMS) else (2 if is_test else 1)
    return (priority, len(parts), path.lower())


def fetch_repository_source_files(
    solution_link: str,
    *,
    max_files: int = MAX_FILES,
    max_total_chars: int = MAX_TOTAL_CHARS,
) -> list[tuple[str, str]]:
    owner, repo = parse_github_repo_url(solution_link)
    base_api = f'https://api.github.com/repos/{owner}/{repo}'

    with httpx.Client(timeout=6.0, headers=get_github_headers(), follow_redirects=True) as client:
        tree_resp = client.get(f'{base_api}/git/trees/HEAD', params={'recursive': '1'})
        if tree_resp.status_code != 200:
            repo_resp = client.get(base_api)
            if repo_resp.status_code != 200:
                return []
            branch = (repo_resp.json().get('default_branch') or '').strip()
            if not branch:
                return []
            tree_resp = client.get(f'{base_api}/git/trees/{quote(branch, safe="")}', params={'recursive': '1'})
            if tree_resp.status_code != 200:
                return []

        tree_items = tree_resp.json().get('tree') or []
        candidates = [
            item['path']
            for item in tree_items
            if isinstance(item, dict)
            and item.get('type') == 'blob'
            and 0 < int(item.get('size') or 1) <= 200_000
            and _is_candidate_source_path(item.get('path', ''))
        ]
        candidates.sort(key=_score_source_path)
        selected_paths = candidates[:max_files]

        collected: list[tuple[str, str]] = []
        remaining = max_total_chars
        for rel_path in selected_paths:
            if remaining <= 0:
                break
            encoded_path = '/'.join(quote(seg, safe='') for seg in rel_path.split('/'))
            file_resp = client.get(f'{base_api}/contents/{encoded_path}')
            if file_resp.status_code != 200:
                continue
            payload = file_resp.json()
            if not isinstance(payload, dict):
                continue
            raw_content = payload.get('content') or ''
            encoding = (payload.get('encoding') or '').lower()
            try:
                if encoding == 'base64' and raw_content:
                    text = base64.b64decode(raw_content).decode('utf-8', errors='replace')
                elif isinstance(raw_content, str):
                    text = raw_content
                else:
                    continue
            except (ValueError, TypeError):
                continue
            text = text.strip()
            if not text:
                continue
            snippet = text[:remaining]
            collected.append((rel_path, snippet))
            remaining -= len(snippet)
        return collected


def _truncate_feedback(text: str, limit: int = MAX_FEEDBACK_CHARS) -> str:
    cleaned = (text or '').strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + '...'


def generate_ai_code_review(
    *,
    solution_link: str,
    task_title: str,
    task_description: str,
) -> str:
    api_key = os.getenv('AI_REVIEW_API_KEY', '').strip()
    if not api_key:
        return (
            'ℹ️ Автоматический AI-разбор не активен (ключ AI_REVIEW_API_KEY не задан). '
            'Работа ожидает проверки ментором.'
        )

    try:
        files = fetch_repository_source_files(solution_link)
    except (GitHubValidationError, httpx.HTTPError, ValueError) as exc:
        logger.warning('AI review GitHub fetch failed: %s', type(exc).__name__)
        return '⚠️ Не удалось выгрузить файлы репозитория из GitHub для автоматического AI-разбора.'

    if not files:
        return 'ℹ️ В репозитории не найдено исходных файлов (.py, .js, .ts, .html, .css) для AI-анализа.'

    code_blocks = '\n\n'.join(f'--- FILE: {path} ---\n{content}' for path, content in files)
    user_prompt = (
        f"Задание: {task_title}\n"
        f"Описание ТЗ:\n{(task_description or '')[:1500]}\n\n"
        f"Исходный код репозитория ({len(files)} файл.):\n{code_blocks[:MAX_TOTAL_CHARS]}"
    )

    base_url = (os.getenv('AI_REVIEW_BASE_URL', 'https://api.openai.com/v1') or 'https://api.openai.com/v1').strip().rstrip('/')
    model = (os.getenv('AI_REVIEW_MODEL', 'gpt-4o-mini') or 'gpt-4o-mini').strip()

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f'{base_url}/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': user_prompt},
                    ],
                    'temperature': 0.2,
                    'max_tokens': 350,
                },
            )
            if resp.status_code != 200:
                logger.warning('AI review API returned HTTP %s', resp.status_code)
                return f'⚠️ Сервис AI-разбора временно недоступен (HTTP {resp.status_code}).'
            data = resp.json()
            choices = data.get('choices') or []
            content = ((choices[0].get('message') or {}).get('content') or '') if choices else ''
            if not content.strip():
                return 'ℹ️ AI-модель вернула пустой ответ. Требуется ручная проверка ментором.'
            return _truncate_feedback(content, MAX_FEEDBACK_CHARS)
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        logger.warning('AI review completion failed: %s', type(exc).__name__)
        return '⚠️ Не удалось получить ответ от сервиса AI-разбора (таймаут или ошибка сети).'


def run_ai_review_for_submission(submission_id: str, *, notify_mentors: bool = False) -> bool:
    submission = (
        Submission.objects.select_related('user', 'user__mentor', 'task')
        .filter(pk=submission_id)
        .first()
    )
    if not submission:
        return True

    feedback = generate_ai_code_review(
        solution_link=submission.solution_link,
        task_title=submission.task.title if submission.task_id else '',
        task_description=submission.task.description if submission.task_id else '',
    )
    reviewed_at = timezone.now()
    Submission.objects.filter(pk=submission.pk).update(
        ai_feedback=feedback,
        ai_reviewed_at=reviewed_at,
        updated_at=reviewed_at,
    )
    submission.ai_feedback = feedback
    submission.ai_reviewed_at = reviewed_at

    if notify_mentors:
        from admin_panel.services.telegram_service import notify_submission_created
        notify_submission_created(submission)
    return True
