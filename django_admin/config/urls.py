from admin_panel.views.shop_views import MyShopOrdersView, ShopBalanceView, ShopOrdersView, ShopProductsView
from admin_panel.views.auth_views import CsrfTokenView
from admin_panel.views.subscription_views import SubscriptionGrantView, PasswordResetView
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.templatetags.static import static
from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularJSONAPIView,
)
from admin_panel.views import (
    RegisterView,
    LoginView,
    RefreshTokenView,
    LogoutView,
    CurrentUserView,
    ChangePasswordView,
    AvatarUploadView,
    BannerUploadView,
    EasterEggView,
    UserAchievementsListView,
    TelegramConnectView,
    TelegramDisconnectView,
    LessonsListView,
    TasksListView,
    TaskDetailView,
    SubmissionsView,
    SubmissionDetailView,
    AchievementsCatalogView,
    LeaderboardView,
    AdminUsersListView,
    AdminUserRoleView,
    AdminScoreAdjustmentView,
    AdminStatsView,
    SystemConfigView,
    HealthCheckView,
    MediaAssetDetailView,
    MediaPresetsCatalogView,
    PresetBannerDetailView,
    PresetAvatarDetailView,
    PresetIconDetailView,
    TelegramWebhookView,
)


def favicon_redirect(request):
    return HttpResponseRedirect(static('admin_panel/favicon.ico'))


urlpatterns = [
    path('api/v1/auth/csrf', CsrfTokenView.as_view()),
    path('api/v1/admin/subscriptions/grant', SubscriptionGrantView.as_view()),
    path('api/v1/auth/reset-password', PasswordResetView.as_view()),
    # Static & Admin
    path('favicon.ico', favicon_redirect, name='favicon'),
    path('admin/', admin.site.urls),

    # OpenAPI 3.0.3 Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/docs-json/', SpectacularJSONAPIView.as_view(), name='schema-json'),

    # System & Health
    path('api/v1/system/config', SystemConfigView.as_view(), name='system-config'),
    path('api/v1/health', HealthCheckView.as_view(), name='health-check'),

    # Authentication
    path('api/v1/auth/register', RegisterView.as_view(), name='auth-register'),
    path('api/v1/auth/login', LoginView.as_view(), name='auth-login'),
    path('api/v1/auth/refresh', RefreshTokenView.as_view(), name='auth-refresh'),
    path('api/v1/auth/logout', LogoutView.as_view(), name='auth-logout'),

    # Current User Profile & Settings
    path('api/v1/users/me', CurrentUserView.as_view(), name='users-me'),
    path('api/v1/users/me/password', ChangePasswordView.as_view(), name='users-me-password'),
    path('api/v1/users/me/avatar', AvatarUploadView.as_view(), name='users-me-avatar'),
    path('api/v1/users/me/banner', BannerUploadView.as_view(), name='users-me-banner'),
    path('api/v1/users/me/easter-egg', EasterEggView.as_view(), name='users-me-easter-egg'),
    path('api/v1/users/me/achievements', UserAchievementsListView.as_view(), name='users-me-achievements'),
    path('api/v1/users/me/telegram/connect', TelegramConnectView.as_view(), name='users-me-tg-connect'),
    path('api/v1/users/me/telegram/disconnect', TelegramDisconnectView.as_view(), name='users-me-tg-disconnect'),

    # Media Storage & Presets
    path('api/v1/media/presets', MediaPresetsCatalogView.as_view(), name='media-presets'),
    path('api/v1/media/presets/banners/<str:slug>', PresetBannerDetailView.as_view(), name='media-preset-banner'),
    path('api/v1/media/presets/avatars/<str:slug>', PresetAvatarDetailView.as_view(), name='media-preset-avatar'),
    path('api/v1/media/presets/icons/<str:slug>', PresetIconDetailView.as_view(), name='media-preset-icon'),
    path('api/v1/media/<str:id>', MediaAssetDetailView.as_view(), name='media-detail'),

    # Curriculum: Lessons & Tasks
    path('api/v1/lessons', LessonsListView.as_view(), name='lessons-list'),
    path('api/v1/tasks', TasksListView.as_view(), name='tasks-list'),
    path('api/v1/tasks/<str:id>', TaskDetailView.as_view(), name='task-detail'),

    # Submissions (Homework)
    path('api/v1/submissions', SubmissionsView.as_view(), name='submissions-list'),
    path('api/v1/submissions/<str:id>', SubmissionDetailView.as_view(), name='submission-detail'),

    # Gamification: Achievements & Leaderboard
    path('api/v1/achievements', AchievementsCatalogView.as_view(), name='achievements-catalog'),
    path('api/v1/leaderboard', LeaderboardView.as_view(), name='leaderboard'),

    path('api/v1/shop/balance', ShopBalanceView.as_view(), name='shop-balance'),
    path('api/v1/shop/products', ShopProductsView.as_view(), name='shop-products'),
    path('api/v1/shop/orders', ShopOrdersView.as_view(), name='shop-orders'),
    path('api/v1/shop/orders/my', MyShopOrdersView.as_view(), name='shop-orders-my'),

    # Mentor & Admin Management
    path('api/v1/admin/users', AdminUsersListView.as_view(), name='admin-users'),
    path('api/v1/admin/users/<str:id>/role', AdminUserRoleView.as_view(), name='admin-user-role'),
    path('api/v1/admin/score-adjustments', AdminScoreAdjustmentView.as_view(), name='admin-score-adjustments'),
    path('api/v1/admin/stats', AdminStatsView.as_view(), name='admin-stats'),

    # Telegram Bot Webhook
    path('api/v1/telegram/webhook', TelegramWebhookView.as_view(), name='telegram-webhook'),
]
