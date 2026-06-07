from django.contrib import admin

from wallet.models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "created_at",
        "updated_at",
    )
    search_fields = ("name", "owner__username")
    list_filter = ("updated_at",)

    readonly_fields = ("created_at", "updated_at")
