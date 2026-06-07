from datetime import datetime

from django.contrib import admin
from django.template.defaultfilters import date as date_filter
from django.utils.html import format_html

from wallet.models import Transaction, TransferGroup, Wallet
from wallet.services import WalletBalanceService


class TransactionInline(admin.TabularInline):
    model = Transaction
    fields = ("type", "wallet", "amount", "date", "description")
    readonly_fields = ("type", "wallet", "amount", "date", "description")
    extra = 0
    max_num = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class WalletTransactionInline(admin.TabularInline):
    model = Transaction
    fields = ("type", "amount", "date", "description")
    readonly_fields = ("type", "amount", "date", "description")
    extra = 0
    max_num = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    inlines = [WalletTransactionInline]
    list_display = (
        "name",
        "owner",
        "display_balance",
        "transaction_count",
        "can_be_negative",
        "display_created_at",
    )
    search_fields = ("name", "owner__username")
    list_filter = ("can_be_negative", "updated_at")
    readonly_fields = ("display_balance", "transaction_count", "display_created_at", "updated_at")
    fields = ("owner", "name", "can_be_negative", "display_balance", "transaction_count", "display_created_at", "updated_at")

    @admin.display(description="Balance")
    def display_balance(self, obj):
        balance = WalletBalanceService.get_balance(obj)
        return f"${balance:,.2f}"

    @admin.display(description="Transactions")
    def transaction_count(self, obj):
        return obj.transactions.count()

    @admin.display(description="Created")
    def display_created_at(self, obj):
        return date_filter(datetime.fromtimestamp(obj.uuid.time / 1000), "M j, Y, P")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "wallet",
        "type",
        "display_amount",
        "date",
        "short_description",
        "transfer_group_link",
    )
    list_filter = ("type", "date", "wallet")
    search_fields = ("description", "wallet__name", "wallet__owner__username")
    readonly_fields = ("uuid", "updated_at", "display_created_at")
    fields = (
        "type",
        "wallet",
        "amount",
        "description",
        "date",
        "transfer_group",
        "uuid",
        "display_created_at",
        "updated_at",
    )

    @admin.display(description="Amount")
    def display_amount(self, obj):
        return f"${obj.amount:,.2f}"

    @admin.display(description="Description")
    def short_description(self, obj):
        return obj.description[:60] if obj.description else "—"

    @admin.display(description="Transfer")
    def transfer_group_link(self, obj):
        if not obj.transfer_group_id:
            return "—"
        url = f"/admin/wallet/transfergroup/{obj.transfer_group_id}/change/"
        return format_html('<a href="{}">View group</a>', url)

    @admin.display(description="Created")
    def display_created_at(self, obj):
        return date_filter(datetime.fromtimestamp(obj.uuid.time / 1000), "M j, Y, P")


@admin.register(TransferGroup)
class TransferGroupAdmin(admin.ModelAdmin):
    list_display = ("uuid", "display_from", "display_to", "display_amount", "display_date")
    readonly_fields = ("uuid", "display_created_at", "updated_at")
    fields = ("uuid", "display_created_at", "updated_at")
    inlines = [TransactionInline]

    @admin.display(description="From")
    def display_from(self, obj):
        tx = obj.transactions.filter(type=Transaction.Type.TRANSFER_OUT).first()
        return str(tx.wallet) if tx else "—"

    @admin.display(description="To")
    def display_to(self, obj):
        tx = obj.transactions.filter(type=Transaction.Type.TRANSFER_IN).first()
        return str(tx.wallet) if tx else "—"

    @admin.display(description="Amount")
    def display_amount(self, obj):
        tx = obj.transactions.first()
        return f"${tx.amount:,.2f}" if tx else "—"

    @admin.display(description="Date")
    def display_date(self, obj):
        tx = obj.transactions.first()
        return tx.date if tx else "—"

    @admin.display(description="Created")
    def display_created_at(self, obj):
        return date_filter(datetime.fromtimestamp(obj.uuid.time / 1000), "M j, Y, P")
