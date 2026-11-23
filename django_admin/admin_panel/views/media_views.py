from admin_panel.serializers import (
    EmptyRequestSerializer,
    ErrorResponseSerializer,
    MediaPresetsCatalogResponseSerializer,
)
import re
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from admin_panel.models import MediaAsset
from admin_panel.services.media_presets import (
    find_preset_banner,
    find_preset_avatar,
    get_all_media_presets_catalog,
)
from admin_panel.achievement_icons import find_preset_icon


class MediaAssetDetailView(APIView):
    serializer_class = EmptyRequestSerializer
    """
    Streams raw image binary (WebP, PNG, JPEG, GIF) stored in PostgreSQL MediaAsset table.
    """
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Получить медиа-ассет по ID (WebP / PNG / JPEG / GIF)",
        description="Возвращает оптимизированное бинарное изображение с кеширующими заголовками.",
        parameters=[
            OpenApiParameter(name="id", location=OpenApiParameter.PATH, description="UUID медиафайла", type=str),
        ],
        responses={
            200: OpenApiResponse(response=OpenApiTypes.BINARY, description="Бинарные данные изображения"),
            404: ErrorResponseSerializer,
            415: ErrorResponseSerializer,
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

        if asset.mime_type not in ('image/webp', 'image/png', 'image/jpeg', 'image/gif'):
            return Response({'message': 'Unsupported legacy media'}, status=415)
        data_bytes = bytes(asset.data)
        response = HttpResponse(data_bytes, content_type=asset.mime_type)
        response['Content-Length'] = len(data_bytes)
        response['Cache-Control'] = 'public, max-age=31536000, immutable'
        response['Cross-Origin-Resource-Policy'] = 'cross-origin'
        return response


class MediaPresetsCatalogView(APIView):
    serializer_class = EmptyRequestSerializer
    """
    Returns curated catalog of default Dark Zinc & Amber banners, avatars, and achievement icons.
    """
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Каталог предустановленных медиа-ассетов",
        description="Возвращает списки готовых баннеров, аватарок и иконок достижений со встроенными dataUri и URL.",
        responses={200: MediaPresetsCatalogResponseSerializer},
    )
    def get(self, request):
        catalog = get_all_media_presets_catalog(request=request)
        return Response(catalog)


class PresetBannerDetailView(APIView):
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Получить SVG-баннер по slug",
        responses={
            200: OpenApiResponse(response=OpenApiTypes.BINARY, description="SVG-изображение"),
            404: ErrorResponseSerializer,
        },
    )
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
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Получить SVG-аватар по slug",
        responses={
            200: OpenApiResponse(response=OpenApiTypes.BINARY, description="SVG-изображение"),
            404: ErrorResponseSerializer,
        },
    )
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
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Получить SVG-иконку ачивки по slug",
        responses={
            200: OpenApiResponse(response=OpenApiTypes.BINARY, description="SVG-изображение"),
            404: ErrorResponseSerializer,
        },
    )
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
