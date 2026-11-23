import io
import warnings
from PIL import Image, ImageOps
from django.db import transaction
from admin_panel.models import MediaAsset, User

LIMITS = {'AVATAR': 2 * 1024**2, 'BANNER': 5 * 1024**2, 'ACHIEVEMENT_ICON': 512 * 1024, 'GENERAL': 5 * 1024**2}
FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF'}
MAX_PIXELS = 16_000_000


def get_media_limit(kind: str) -> int:
    from admin_panel.services.settings_service import get_setting
    if kind == 'AVATAR':
        return max(1, int(get_setting('avatar_max_mb', 2) or 2)) * 1024 * 1024
    if kind == 'BANNER':
        return max(1, int(get_setting('banner_max_mb', 5) or 5)) * 1024 * 1024
    return LIMITS[kind]


def read_upload(file, kind):
    limit = get_media_limit(kind)
    if file.size > limit:
        raise ValueError('Файл превышает допустимый размер.')
    data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Файл превышает допустимый размер.')
    return data


def validate_image_buffer(buffer, mime_type, kind='GENERAL'):
    clean_mime = (mime_type or '').split(';', 1)[0].strip().lower()
    if clean_mime not in {'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'}:
        raise ValueError('Разрешены только JPEG, PNG, WebP и GIF. SVG запрещён.')
    if len(buffer) > get_media_limit(kind):
        raise ValueError('Файл превышает допустимый размер.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(buffer)) as source:
                if source.format not in FORMATS or source.width * source.height > MAX_PIXELS:
                    raise ValueError('Недопустимый формат или размер изображения.')
                source.verify()
            with Image.open(io.BytesIO(buffer)) as source:
                image = ImageOps.exif_transpose(source).convert('RGBA')
                if kind in ('AVATAR', 'BANNER'):
                    image = ImageOps.fit(image, (256, 256) if kind == 'AVATAR' else (1600, 400), method=Image.Resampling.LANCZOS)
                elif kind == 'ACHIEVEMENT_ICON':
                    image.thumbnail((128, 128))
                else:
                    image.thumbnail((1200, 1200))
                output = io.BytesIO()
                image.save(output, format='WEBP', quality=85)
                return output.getvalue()
    except (OSError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValueError('Не удалось прочитать безопасное растровое изображение.') from exc


@transaction.atomic
def save_optimized_media_asset(buffer, mime_type, kind='GENERAL', owner_id=None):
    webp_bytes = validate_image_buffer(buffer, mime_type, kind=kind)
    user = User.objects.select_for_update().get(pk=owner_id) if owner_id else None
    asset = MediaAsset.objects.create(kind=kind, mime_type='image/webp', data=webp_bytes, size_bytes=len(webp_bytes), owner_id=owner_id)
    if user and kind in ('AVATAR', 'BANNER'):
        field = 'avatar_url' if kind == 'AVATAR' else 'banner_url'
        User.objects.filter(pk=user.pk).update(**{field: f'/api/v1/media/{asset.pk}'})
        MediaAsset.objects.filter(owner_id=owner_id, kind=kind).exclude(pk=asset.pk).delete()
    return {'id': asset.pk, 'url': f'/api/v1/media/{asset.pk}', 'mimeType': 'image/webp', 'sizeBytes': asset.size_bytes}
