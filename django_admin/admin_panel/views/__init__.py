from .auth_views import RegisterView, LoginView, RefreshTokenView, LogoutView
from .user_views import (
    CurrentUserView,
    ChangePasswordView,
    AvatarUploadView,
    BannerUploadView,
    EasterEggView,
    ClaimEasterEggAliasView,
    UserAchievementsListView,
    TelegramConnectView,
    TelegramDisconnectView,
)
from .curriculum_views import (
    LessonsListView,
    TasksListView,
    TaskDetailView,
    SubmissionsView,
    SubmissionDetailView,
)
from .gamification_views import AchievementsCatalogView, AchievementDetailView, LeaderboardView
from .admin_views import (
    AdminUsersListView,
    AdminUserRoleView,
    AdminScoreAdjustmentView,
    AdminStatsView,
)
from .system_views import SystemConfigView, HealthCheckView
from .media_views import (
    InstructionPdfView,
    MediaAssetDetailView,
    MediaPresetsCatalogView,
    PresetBannerDetailView,
    PresetAvatarDetailView,
    PresetIconDetailView,
)
from .telegram_views import TelegramWebhookView
