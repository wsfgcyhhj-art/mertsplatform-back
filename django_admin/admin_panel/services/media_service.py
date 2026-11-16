import io
from typing import Optional, Literal
from PIL import Image, ImageOps
from admin_panel.models import MediaAsset

ALLOWED_IMAGE_MIMES = {
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
    'image/gif',
    'image/svg+xml',
}

KindType = Literal['AVATAR', 'BANNER', 'ACHIEVEMENT_ICON', 'GENERAL']


def save_optimized_media_asset(
    buffer: bytes,
    mime_type: str,
    kind: KindType = 'GENERAL',
    owner_id: Optional[str] = None,
) -> dict:
    """
    Optimizes uploaded image (WebP) using Pillow, persists in Neon PostgreSQL MediaAsset table,
    and removes previous asset of the same kind for owner_id to prevent storage bloat.
    """
    normalized_mime = mime_type.lower().strip()
    if normalized_mime not in ALLOWED_IMAGE_MIMES:
        raise ValueError('Неподдерживаемый формат изображения. Разрешены: JPEG, PNG, WebP, GIF, SVG')

    if normalized_mime == 'image/svg+xml':
        head = buffer[:512].decode('utf-8', errors='ignore').lower()
        if '<svg' not in head:
            raise ValueError('Некорректный SVG-файл: отсутствует тег <svg>')
        output_buffer = buffer
        output_mime = 'image/svg+xml'
    else:
        try:
            image = Image.open(io.BytesIO(buffer))
        except Exception as e:
            raise ValueError(f'Не удалось прочитать изображение: {str(e)}')

        # Convert palette/transparency to RGBA or RGB
        if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
            image = image.convert('RGBA')
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        if kind == 'AVATAR':
            # 256x256 cover crop
            image = ImageOps.fit(image, (256, 256), method=Image.Resampling.LANCZOS)
            quality = 85
        elif kind == 'BANNER':
            # 1600x400 cover crop
            image = ImageOps.fit(image, (1600, 400), method=Image.Resampling.LANCZOS)
            quality = 85
        elif kind == 'ACHIEVEMENT_ICON':
            image.thumbnail((128, 128), Image.Resampling.LANCZOS)
            quality = 90
        else:
            quality = 85

        out_io = io.BytesIO()
        image.save(out_io, format='WEBP', quality=quality)
        output_buffer = out_io.getvalue()
        output_mime = 'image/webp'

    # Auto-cleanup previous user media to prevent storage leaks
    if owner_id and kind in ('AVATAR', 'BANNER'):
        try:
            MediaAsset.objects.filter(owner_id=owner_id, kind=kind).delete()
        except Exception:
            pass

    asset = MediaAsset.objects.create(
        kind=kind,
        mime_type=output_mime,
        data=output_buffer,
        size_bytes=len(output_buffer),
        owner_id=owner_id,
    )

    return {
        'id': asset.id,
        'url': f'/api/v1/media/{asset.id}',
        'mimeType': asset.mime_type,
        'sizeBytes': asset.size_bytes,
    }
