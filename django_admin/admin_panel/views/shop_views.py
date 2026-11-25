from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

from admin_panel.achievement_icons import to_absolute_media_url
from admin_panel.api_utils import qparam, parse_bool_param, resolve_ordering, paginate_list_or_qs
from admin_panel.models import ShopItemTypeChoices, ShopOrder, ShopOrderStatus, ShopProduct
from admin_panel.serializers import PaginatedMetaMixin
from admin_panel.services.shop_service import ShopConflict, place_order, shop_balance
from admin_panel.throttles import ShopOrderThrottle


class ShopBalanceSerializer(serializers.Serializer):
    totalEarnedPoints = serializers.IntegerField()
    spentPoints = serializers.IntegerField()
    availableCoins = serializers.IntegerField()


class ShopProductSerializer(serializers.ModelSerializer):
    priceSom = serializers.IntegerField(source='price_som')
    priceCoins = serializers.IntegerField(source='price_coins')
    itemType = serializers.ChoiceField(source='item_type', choices=ShopItemTypeChoices.choices)
    metadata = serializers.JSONField()
    imageUrl = serializers.SerializerMethodField()

    class Meta:
        model = ShopProduct
        fields = ('id', 'title', 'description', 'itemType', 'metadata', 'priceSom', 'priceCoins', 'imageUrl', 'stock')

    def get_imageUrl(self, obj) -> str:
        url = obj.image_url or ''
        return to_absolute_media_url(url, request=self.context.get('request')) or ''


class ShopOrderSerializer(serializers.ModelSerializer):
    productId = serializers.CharField(source='product_id')
    productTitle = serializers.CharField(source='product.title')
    priceCoins = serializers.IntegerField(source='price_coins')
    createdAt = serializers.DateTimeField(source='created_at')
    processedAt = serializers.DateTimeField(source='processed_at', allow_null=True)

    class Meta:
        model = ShopOrder
        fields = ('id', 'productId', 'productTitle', 'priceCoins', 'status', 'comment', 'createdAt', 'processedAt')


class ShopPurchaseSerializer(serializers.Serializer):
    productId = serializers.CharField(max_length=64)
    comment = serializers.CharField(max_length=500, required=False, default='', allow_blank=True)
    requestId = serializers.UUIDField(required=False, help_text='Повторите тот же UUID при повторной отправке заказа.')
    expectedPriceCoins = serializers.IntegerField(required=False, min_value=0)


class ShopCatalogSerializer(ShopBalanceSerializer, PaginatedMetaMixin):
    products = ShopProductSerializer(many=True)


class ShopPurchaseResponseSerializer(ShopBalanceSerializer):
    order = ShopOrderSerializer()


class ShopErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class ShopBalanceView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses=ShopBalanceSerializer, summary='Баланс магазина')
    def get(self, request):
        return Response(shop_balance(request.user))


class ShopProductsView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        responses=ShopCatalogSerializer,
        summary='Активные товары и баланс магазина',
        parameters=[
            OpenApiParameter(name='search', type=str, description='Поиск по названию или описанию'),
            OpenApiParameter(name='inStock', type=bool, description='Только товары в наличии'),
            OpenApiParameter(name='ordering', type=str, description='Сортировка (order, priceCoins, title, stock)'),
            OpenApiParameter(name='page', type=int, description='Номер страницы'),
            OpenApiParameter(name='limit', type=int, description='Размер страницы'),
        ],
    )
    def get(self, request):
        products = ShopProduct.objects.filter(is_active=True)
        search = (qparam(request, 'search') or '').strip()
        if search:
            products = products.filter(Q(title__icontains=search) | Q(description__icontains=search))
        in_stock = parse_bool_param(qparam(request, 'inStock', 'in_stock'))
        if in_stock is True:
            products = products.filter(stock__gt=0)
        elif in_stock is False:
            products = products.filter(stock=0)
        ordering = resolve_ordering(
            qparam(request, 'ordering'),
            {'order': 'order', 'priceCoins': 'price_coins', 'priceSom': 'price_som', 'title': 'title', 'stock': 'stock'},
            ['order', 'title'],
        )
        products = products.order_by(*ordering)
        page_meta, items = paginate_list_or_qs(request, products)
        if isinstance(page_meta, dict) and 'error' in page_meta:
            return Response({'message': page_meta['error']}, status=400)
        data = ShopProductSerializer(items, many=True, context={'request': request}).data
        payload = {'products': data, **shop_balance(request.user)}
        if page_meta is not None:
            payload.update(page_meta)
        return Response(payload)


class ShopOrdersView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (ShopOrderThrottle,)

    @extend_schema(
        request=ShopPurchaseSerializer,
        responses={200: ShopPurchaseResponseSerializer, 201: ShopPurchaseResponseSerializer,
                   404: ShopErrorSerializer, 409: ShopErrorSerializer},
        summary='Покупка товара за баллы',
    )
    def post(self, request):
        serializer = ShopPurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            order, balance, created = place_order(
                request.user, data['productId'], data['comment'], data.get('requestId'), data.get('expectedPriceCoins')
            )
        except ShopProduct.DoesNotExist:
            raise NotFound('Товар недоступен.')
        except ShopConflict as error:
            return Response({'detail': str(error)}, status=409)
        return Response({'order': ShopOrderSerializer(order).data, **balance}, status=201 if created else 200)


class MyShopOrdersView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        responses=ShopOrderSerializer(many=True),
        summary='История покупок студента',
        parameters=[
            OpenApiParameter(name='status', type=str, description='Фильтр по статусу (PENDING, COMPLETED, CANCELLED)'),
            OpenApiParameter(name='ordering', type=str, description='Сортировка (createdAt, priceCoins, status)'),
        ],
    )
    def get(self, request):
        orders = request.user.shop_orders.select_related('product')
        st = (qparam(request, 'status') or '').strip().upper()
        if st:
            if st not in ShopOrderStatus.values:
                return Response({'message': 'Invalid status filter'}, status=400)
            orders = orders.filter(status=st)
        ordering = resolve_ordering(
            qparam(request, 'ordering'),
            {'createdAt': 'created_at', 'priceCoins': 'price_coins', 'status': 'status'},
            ['-created_at', '-id'],
        )
        orders = orders.order_by(*ordering)[:200]
        return Response(ShopOrderSerializer(orders, many=True).data)
