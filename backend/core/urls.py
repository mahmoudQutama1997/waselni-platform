from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet, OrderViewSet, RatingViewSet, SettlementViewSet, DelayReportViewSet,
    SupportTicketViewSet, DashboardSummaryView, MerchantViewSet, MerchantProfileSelfView,
    CaptainSelfView, CaptainScheduleView, CaptainServicePreferenceView, CaptainEarningsView,
    AdminOperationsView, AdminUsersView, AdminUserDetailView, FinanceAccessAuditView,
    AdminAccountAuditView, AdminUserSubscriptionView, AdminSubscriptionPaymentView,
    AdminSubscriptionsView, AdminCaptainApprovalView, AdminCaptainServicesView,
    ChangePasswordView, AccountProfileView, AdminStoresView, MerchantReportsView,
    NotificationListView, NotificationReadView, CustomerDeliveryRequestView,
)
from .merchant_views import (
    MerchantDashboardView, MerchantAnalyticsView, MerchantBranchesView,
    MerchantBranchDetailView, MerchantStaffView, MerchantStaffDetailView,
    MerchantHoursView, MerchantClosuresView, MerchantStoreStatusView,
    MerchantPriceHistoryView, MerchantInventoryLedgerView,
)
from .control_views import (
    AdminBranchesView, AdminBusinessCategoriesView, AdminBusinessCategoryDetailView,
    AdminControlMeView, AdminPlatformSettingsView, AdminProvidersView,
    AdminRegionDetailView, AdminRegionsView, AdminServiceDetailView, AdminServicesView,
    AdminStaffView, BusinessCategoryListView, ServiceCatalogView, AdminPharmacyProductsView,
)
from .control_ops import (
    AdminAlertsView, AdminAnalyticsView, AdminAuditLogView, AdminFinanceCenterView,
    AdminMapView, AdminOperationsCenterView, AdminOrderDetailView, AdminSupportCenterView,
)

router = DefaultRouter()
router.register("merchants", MerchantViewSet, basename="merchant")
router.register("products", ProductViewSet, basename="product")
router.register("orders", OrderViewSet, basename="order")
router.register("ratings", RatingViewSet, basename="rating")
router.register("settlements", SettlementViewSet, basename="settlement")
router.register("delay-reports", DelayReportViewSet, basename="delay-report")
router.register("support-tickets", SupportTicketViewSet, basename="support-ticket")

urlpatterns = [
    path("notifications/", NotificationListView.as_view()),
    path("notifications/read-all/", NotificationReadView.as_view()),
    path("notifications/<int:notification_id>/read/", NotificationReadView.as_view()),
    path("merchant/profile/", MerchantProfileSelfView.as_view()),
    path("merchant/reports/", MerchantReportsView.as_view()),
    path("merchant/dashboard/", MerchantDashboardView.as_view()),
    path("merchant/analytics/", MerchantAnalyticsView.as_view()),
    path("merchant/branches/", MerchantBranchesView.as_view()),
    path("merchant/branches/<int:branch_id>/", MerchantBranchDetailView.as_view()),
    path("merchant/staff/", MerchantStaffView.as_view()),
    path("merchant/staff/<int:staff_id>/", MerchantStaffDetailView.as_view()),
    path("merchant/hours/", MerchantHoursView.as_view()),
    path("merchant/closures/", MerchantClosuresView.as_view()),
    path("merchant/status/", MerchantStoreStatusView.as_view()),
    path("merchant/price-changes/", MerchantPriceHistoryView.as_view()),
    path("merchant/inventory/movements/", MerchantInventoryLedgerView.as_view()),
    path("account/change-password/", ChangePasswordView.as_view()),
    path("account/profile/", AccountProfileView.as_view()),
    path("admin/users/", AdminUsersView.as_view()),
    path("admin/finance-audit/", FinanceAccessAuditView.as_view()),
    path("admin/account-audit/", AdminAccountAuditView.as_view()),
    path("admin/stores/", AdminStoresView.as_view()),
    path("admin/stores/<int:store_id>/", AdminStoresView.as_view()),
    path("admin/users/<int:user_id>/", AdminUserDetailView.as_view()),
    path("admin/users/<int:user_id>/subscription/", AdminUserSubscriptionView.as_view()),
    path("admin/subscriptions/", AdminSubscriptionsView.as_view()),
    path("admin/subscriptions/<int:subscription_id>/", AdminSubscriptionsView.as_view()),
    path("admin/subscriptions/<int:subscription_id>/payments/", AdminSubscriptionPaymentView.as_view()),
    path("captains/me/", CaptainSelfView.as_view()),
    path("captains/me/schedule/", CaptainScheduleView.as_view()),
    path("captains/me/services/", CaptainServicePreferenceView.as_view()),
    path("captains/me/earnings/", CaptainEarningsView.as_view()),
    path("admin/captains/<int:captain_profile_id>/approval/", AdminCaptainApprovalView.as_view()),
    path("admin/captains/<int:captain_profile_id>/services/", AdminCaptainServicesView.as_view()),
    path("", include(router.urls)),
    path("orders/service/<str:service>/", CustomerDeliveryRequestView.as_view()),
    path("dashboard/summary/", DashboardSummaryView.as_view()),
    path("admin/operations/", AdminOperationsView.as_view()),
    # Admin control center
    path("services/", ServiceCatalogView.as_view()),
    path("admin/control/me/", AdminControlMeView.as_view()),
    path("admin/control/services/", AdminServicesView.as_view()),
    path("admin/control/services/<int:service_id>/", AdminServiceDetailView.as_view()),
    path("admin/control/business-categories/", AdminBusinessCategoriesView.as_view()),
    path("admin/control/business-categories/<int:category_id>/", AdminBusinessCategoryDetailView.as_view()),
    path("business-categories/", BusinessCategoryListView.as_view()),
    path("admin/control/pharmacy-products/", AdminPharmacyProductsView.as_view()),
    path("admin/control/pharmacy-products/<int:product_id>/", AdminPharmacyProductsView.as_view()),
    path("admin/control/regions/", AdminRegionsView.as_view()),
    path("admin/control/regions/<int:region_id>/", AdminRegionDetailView.as_view()),
    path("admin/control/providers/", AdminProvidersView.as_view()),
    path("admin/control/providers/<int:store_id>/", AdminProvidersView.as_view()),
    path("admin/control/branches/", AdminBranchesView.as_view()),
    path("admin/control/branches/<int:branch_id>/", AdminBranchesView.as_view()),
    path("admin/control/staff/", AdminStaffView.as_view()),
    path("admin/control/staff/<int:user_id>/", AdminStaffView.as_view()),
    path("admin/control/settings/", AdminPlatformSettingsView.as_view()),
    path("admin/control/operations/", AdminOperationsCenterView.as_view()),
    path("admin/control/operations/<int:order_id>/", AdminOrderDetailView.as_view()),
    path("admin/control/map/", AdminMapView.as_view()),
    path("admin/control/analytics/", AdminAnalyticsView.as_view()),
    path("admin/control/finance/", AdminFinanceCenterView.as_view()),
    path("admin/control/support/", AdminSupportCenterView.as_view()),
    path("admin/control/support/<int:ticket_id>/", AdminSupportCenterView.as_view()),
    path("admin/control/audit/", AdminAuditLogView.as_view()),
    path("admin/control/alerts/", AdminAlertsView.as_view()),
]
