import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from django.utils import timezone

from admin_panel.services.telegram_service import get_bot_token

MAX_INIT_DATA_AGE_SECONDS = 86400


class TelegramWebAppAuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 401):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def verify_telegram_webapp_init_data(init_data: str, *, bot_token: str | None = None) -> dict:
    if not isinstance(init_data, str) or not init_data.strip() or len(init_data) > 8192:
        raise TelegramWebAppAuthError(
            'TMA_INVALID_INIT_DATA',
            'Передан пустой или некорректный initData.',
            status_code=400,
        )

    token = (bot_token if bot_token is not None else get_bot_token()).strip()
    if not token:
        raise TelegramWebAppAuthError(
            'TMA_BOT_NOT_CONFIGURED',
            'Telegram-бот не настроен на сервере.',
            status_code=503,
        )

    pairs = parse_qsl(init_data.strip(), keep_blank_values=True, strict_parsing=False)
    if not pairs:
        raise TelegramWebAppAuthError(
            'TMA_INVALID_INIT_DATA',
            'Не удалось разобрать параметры initData.',
            status_code=400,
        )

    received_hashes = [val for key, val in pairs if key == 'hash']
    if len(received_hashes) != 1 or not received_hashes[0]:
        raise TelegramWebAppAuthError(
            'TMA_MISSING_HASH',
            'Отсутствует криптографическая подпись hash в initData.',
            status_code=401,
        )
    received_hash = received_hashes[0].strip().lower()

    data_pairs = [(key, val) for key, val in pairs if key != 'hash']
    params_dict = dict(data_pairs)
    if len(params_dict) != len(data_pairs):
        raise TelegramWebAppAuthError(
            'TMA_INVALID_INIT_DATA',
            'Обнаружены дублирующиеся параметры в initData.',
            status_code=400,
        )

    raw_auth_date = params_dict.get('auth_date')
    try:
        auth_date = int(str(raw_auth_date).strip())
    except (TypeError, ValueError) as exc:
        raise TelegramWebAppAuthError(
            'TMA_INVALID_AUTH_DATE',
            'Некорректная метка времени auth_date в initData.',
            status_code=401,
        ) from exc

    now_ts = int(timezone.now().timestamp())
    if auth_date > now_ts + 300 or (now_ts - auth_date) > MAX_INIT_DATA_AGE_SECONDS:
        raise TelegramWebAppAuthError(
            'TMA_EXPIRED_INIT_DATA',
            'Срок действия сессии Telegram Mini App истёк. Перезапустите мини-приложение.',
            status_code=401,
        )

    data_check_string = '\n'.join(
        f'{key}={val}' for key, val in sorted(data_pairs, key=lambda item: item[0])
    )
    secret_key = hmac.new(b'WebAppData', token.encode('utf-8'), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise TelegramWebAppAuthError(
            'TMA_INVALID_SIGNATURE',
            'Неверная подпись Telegram WebApp initData.',
            status_code=401,
        )

    raw_user = params_dict.get('user')
    if not raw_user:
        raise TelegramWebAppAuthError(
            'TMA_MISSING_USER',
            'В initData отсутствуют данные пользователя Telegram.',
            status_code=400,
        )

    try:
        user_payload = json.loads(raw_user)
    except ValueError as exc:
        raise TelegramWebAppAuthError(
            'TMA_INVALID_USER_JSON',
            'Повреждён JSON-объект user в initData.',
            status_code=400,
        ) from exc

    if not isinstance(user_payload, dict) or 'id' not in user_payload:
        raise TelegramWebAppAuthError(
            'TMA_MISSING_USER_ID',
            'Отсутствует идентификатор пользователя Telegram.',
            status_code=400,
        )

    try:
        tg_user_id = int(user_payload['id'])
        if tg_user_id <= 0:
            raise ValueError('Non-positive Telegram user id')
    except (TypeError, ValueError) as exc:
        raise TelegramWebAppAuthError(
            'TMA_INVALID_USER_ID',
            'Некорректный идентификатор пользователя Telegram.',
            status_code=400,
        ) from exc

    raw_username = user_payload.get('username')
    tg_username = raw_username.strip().lstrip('@') if isinstance(raw_username, str) and raw_username.strip() else None

    return {
        'telegram_id': str(tg_user_id),
        'telegram_username': tg_username,
        'first_name': str(user_payload.get('first_name') or '').strip(),
        'last_name': str(user_payload.get('last_name') or '').strip(),
        'auth_date': auth_date,
    }
