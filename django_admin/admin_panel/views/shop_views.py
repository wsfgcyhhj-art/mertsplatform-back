from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from admin_panel.models import ShopOrder, ShopProduct
from admin_panel.services.shop_service import ShopConflict, place_order, shop_balance


class ShopBalanceSerializer(serializers.Serializer):
    totalEarnedPoints = serializers.IntegerField()
    spentPoints = serializers.IntegerField()
    availableCoins = serializers.IntegerField()


class ShopProductSerializer(serializers.ModelSerializer):
    priceSom = serializers.IntegerField(source='price_som')
    priceCoins = serializers.IntegerField(source='price_coins')
    imageUrl = serializers.SerializerMethodField()

    class Meta:
        model = ShopProduct
        fields = ('id', 'title', 'description', 'priceSom', 'priceCoins', 'imageUrl', 'stock')

    def get_imageUrl(self, obj) -> str:
        if obj.image_url.startswith('/api/v1/media/') and self.context.get('request'):
            return self.context['request'].build_absolute_uri(obj.image_url)
        return obj.image_url


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


class ShopCatalogSerializer(ShopBalanceSerializer):
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

    @extend_schema(responses=ShopCatalogSerializer, summary='Активные товары и баланс магазина')
    def get(self, request):
        products = ShopProduct.objects.filter(is_active=True)
        data = ShopProductSerializer(products, many=True, context={'request': request}).data
        return Response({'products': data, **shop_balance(request.user)})


class ShopOrdersView(APIView):
    permission_classes = (IsAuthenticated,)

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

    @extend_schema(responses=ShopOrderSerializer(many=True), summary='История покупок студента')
    def get(self, request):
        orders = request.user.shop_orders.select_related('product')
        return Response(ShopOrderSerializer(orders, many=True).data)
