from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets=UserAdmin.fieldsets + (("Waselni",{"fields":("role","phone","identity_number","subscription_required","must_change_password","language","profile_image")}),)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    readonly_fields = [
        "status", "accepted_at", "captain_accepted_at", "merchant_arrived_at",
        "ready_at", "captain_delivered_at", "completed_at", "completed_by",
        "completed_by_name", "completion_method",
    ]

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register([
    MerchantProfile, CaptainProfile, Product, CashSettlement, DelayReport,
    Rating, SupportTicket, Subscription, SubscriptionPayment,
])
