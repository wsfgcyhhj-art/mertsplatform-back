import re
from django.http import HttpResponse, JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from admin_panel.models import MediaAsset
from admin_panel.services.media_presets import (
    find_preset_banner,
    find_preset_avatar,
    get_all_media_presets_catalog,
)
from admin_panel.achievement_icons import find_preset_icon


class MediaAssetDetailView(APIView):
    """
    Streams raw image binary (WebP, SVG, PNG) stored in Neon PostgreSQL MediaAsset table.
    Guarantees persistence across ephemeral cloud container restarts.
    """
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Получить медиа-ассет по ID (WebP / SVG)",
        description="Возвращает оптимизированное бинарное изображение с кеширующими заголовками.",
        parameters=[
            OpenApiParameter(name="id", location=OpenApiParameter.PATH, description="UUID медиафайла", type=str),
        ],
        responses={
            200: OpenApiResponse(description="Бинарные данные изображения"),
            404: OpenApiResponse(description="Медиа-ассет не найден"),
        }
    )
    def get(self, request, id: str):
        clean_id = re.sub(r'\.(webp|svg|png|jpg|jpeg|gif)$', '', id.strip(), flags=re.I)
        try:
            asset = MediaAsset.objects.get(id=clean_id)
        except MediaAsset.DoesNotExist:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Media asset not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        data_bytes = bytes(asset.data)
        response = HttpResponse(data_bytes, content_type=asset.mime_type)
        response['Content-Length'] = len(data_bytes)
        response['Cache-Control'] = 'public, max-age=31536000, immutable'
        response['Cross-Origin-Resource-Policy'] = 'cross-origin'
        return response


class MediaPresetsCatalogView(APIView):
    """
    Returns curated catalog of default Dark Zinc & Amber banners, avatars, and achievement icons.
    """
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Каталог предустановленных медиа-ассетов",
        description="Возвращает списки готовых баннеров, аватарок и иконок достижений со встроенными dataUri и URL.",
    )
    def get(self, request):
        catalog = get_all_media_presets_catalog()
        return Response(catalog)


class PresetBannerDetailView(APIView):
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(summary="Получить SVG-баннер по slug")
    def get(self, request, slug: str):
        preset = find_preset_banner(slug)
        if not preset:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Banner preset not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        response = HttpResponse(preset['svg'], content_type='image/svg+xml; charset=utf-8')
        response['Cache-Control'] = 'public, max-age=86400'
        return response


class PresetAvatarDetailView(APIView):
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(summary="Получить SVG-аватар по slug")
    def get(self, request, slug: str):
        preset = find_preset_avatar(slug)
        if not preset:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Avatar preset not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        response = HttpResponse(preset['svg'], content_type='image/svg+xml; charset=utf-8')
        response['Cache-Control'] = 'public, max-age=86400'
        return response


class PresetIconDetailView(APIView):
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(summary="Получить SVG-иконку ачивки по slug")
    def get(self, request, slug: str):
        preset = find_preset_icon(slug)
        if not preset:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Icon preset not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        response = HttpResponse(preset['svg'], content_type='image/svg+xml; charset=utf-8')
        response['Cache-Control'] = 'public, max-age=86400'
        return response
