import os
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlsplit

import httpx
from django.utils import timezone

from admin_panel.services.settings_service import get_setting

_SEGMENT_RE = re.compile(r'^[A-Za-z0-9_.-]{1,100}$')
_RESERVED_OWNERS = frozenset({
    'settings', 'explore', 'marketplace', 'notifications', 'pulls',
    'issues', 'orgs', 'topics', 'trending', 'search', 'login', 'join', 'gist',
})

MSG_PRIVATE_OR_NOT_FOUND = 'Репозиторий не найден или закрыт (приватный). Откройте доступ и попробуйте снова.'
MSG_REPO_EMPTY = 'Репозиторий пустой — в нём нет ни одного коммита.'
MSG_NO_RECENT_COMMITS = 'В репозитории нет свежих коммитов по этому заданию.'
MSG_INVALID_GITHUB_URL = 'Укажите корректную ссылку на публичный GitHub-репозиторий (https://github.com/owner/repo).'


class GitHubValidationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def get_github_headers() -> dict[str, str]:
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'MertsPlatform-LMS/1.0',
    }
    token = os.getenv('GITHUB_TOKEN', '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def parse_github_repo_url(solution_link: str) -> tuple[str, str]:
    if not isinstance(solution_link, str) or not solution_link.strip():
        raise GitHubValidationError('GITHUB_INVALID_URL', MSG_INVALID_GITHUB_URL)
    cleaned = solution_link.strip()
    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise GitHubValidationError('GITHUB_INVALID_URL', MSG_INVALID_GITHUB_URL) from exc

    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('http', 'https') or host not in ('github.com', 'www.github.com'):
        raise GitHubValidationError('GITHUB_INVALID_URL', MSG_INVALID_GITHUB_URL)

    parts = [seg for seg in (parsed.path or '').split('/') if seg]
    if len(parts) < 2:
        raise GitHubValidationError('GITHUB_INVALID_URL', MSG_INVALID_GITHUB_URL)

    owner, repo = parts[0], parts[1]
    if repo.lower().endswith('.git'):
        repo = repo[:-4]

    if (
        not owner
        or not repo
        or owner in ('.', '..')
        or repo in ('.', '..')
        or owner.lower() in _RESERVED_OWNERS
        or not _SEGMENT_RE.fullmatch(owner)
        or not _SEGMENT_RE.fullmatch(repo)
    ):
        raise GitHubValidationError('GITHUB_INVALID_URL', MSG_INVALID_GITHUB_URL)

    return owner, repo


def _parse_github_iso_datetime(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, dt_timezone.utc)
    return dt


def validate_github_repository(solution_link: str) -> dict:
    owner, repo = parse_github_repo_url(solution_link)
    base_api = f'https://api.github.com/repos/{owner}/{repo}'

    try:
        with httpx.Client(timeout=4.0, headers=get_github_headers(), follow_redirects=True) as client:
            repo_resp = client.get(base_api)
            if repo_resp.status_code == 404:
                raise GitHubValidationError('GITHUB_NOT_FOUND', MSG_PRIVATE_OR_NOT_FOUND)
            if repo_resp.status_code in (401, 403):
                raise GitHubValidationError('GITHUB_REPO_PRIVATE', MSG_PRIVATE_OR_NOT_FOUND)
            if repo_resp.status_code != 200:
                raise GitHubValidationError(
                    'GITHUB_API_ERROR',
                    'Не удалось проверить репозиторий через GitHub API. Попробуйте позже.',
                )

            try:
                repo_data = repo_resp.json()
            except ValueError as exc:
                raise GitHubValidationError(
                    'GITHUB_API_ERROR',
                    'Некорректный ответ от GitHub API.',
                ) from exc

            if not isinstance(repo_data, dict) or repo_data.get('private') is True:
                raise GitHubValidationError('GITHUB_REPO_PRIVATE', MSG_PRIVATE_OR_NOT_FOUND)

            size = int(repo_data.get('size') or 0)
            default_branch = (repo_data.get('default_branch') or '').strip()
            if size <= 0 or not default_branch:
                raise GitHubValidationError('GITHUB_REPO_EMPTY', MSG_REPO_EMPTY)

            commits_resp = client.get(f'{base_api}/commits', params={'per_page': 1})
            if commits_resp.status_code == 409:
                raise GitHubValidationError('GITHUB_REPO_EMPTY', MSG_REPO_EMPTY)
            if commits_resp.status_code in (401, 403):
                raise GitHubValidationError('GITHUB_REPO_PRIVATE', MSG_PRIVATE_OR_NOT_FOUND)
            if commits_resp.status_code == 404:
                raise GitHubValidationError('GITHUB_NOT_FOUND', MSG_PRIVATE_OR_NOT_FOUND)
            if commits_resp.status_code != 200:
                raise GitHubValidationError(
                    'GITHUB_API_ERROR',
                    'Не удалось получить историю коммитов репозитория.',
                )

            try:
                commits_data = commits_resp.json()
            except ValueError as exc:
                raise GitHubValidationError(
                    'GITHUB_API_ERROR',
                    'Некорректный ответ коммитов от GitHub API.',
                ) from exc

            if not isinstance(commits_data, list) or not commits_data:
                raise GitHubValidationError('GITHUB_REPO_EMPTY', MSG_REPO_EMPTY)

            latest = commits_data[0] if isinstance(commits_data[0], dict) else {}
            commit_info = latest.get('commit') if isinstance(latest.get('commit'), dict) else {}
            committer = commit_info.get('committer') if isinstance(commit_info.get('committer'), dict) else {}
            author = commit_info.get('author') if isinstance(commit_info.get('author'), dict) else {}
            commit_date_raw = committer.get('date') or author.get('date')
            commit_dt = _parse_github_iso_datetime(commit_date_raw)
            if commit_dt is None:
                raise GitHubValidationError('GITHUB_NO_RECENT_COMMITS', MSG_NO_RECENT_COMMITS)

            max_age_days = max(1, int(get_setting('github_max_commit_age_days', 30) or 30))
            if (timezone.now() - commit_dt) > timedelta(days=max_age_days):
                raise GitHubValidationError('GITHUB_NO_RECENT_COMMITS', MSG_NO_RECENT_COMMITS)

            return {
                'valid': True,
                'owner': owner,
                'repo': repo,
                'fullName': repo_data.get('full_name') or f'{owner}/{repo}',
                'defaultBranch': default_branch,
                'lastCommitSha': str(latest.get('sha') or ''),
                'lastCommitMessage': str(commit_info.get('message') or '')[:200],
                'lastCommitAt': commit_date_raw,
            }
    except GitHubValidationError:
        raise
    except httpx.HTTPError as exc:
        raise GitHubValidationError(
            'GITHUB_API_ERROR',
            'Не удалось связаться с GitHub API (таймаут или ошибка сети). Попробуйте снова.',
        ) from exc
