from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction as db_transaction

from .models import Category, Transaction, TransferGroup, Wallet


class CategoryService:
    @classmethod
    def create_category(cls, owner, name) -> Category:
        return Category.objects.create(owner=owner, name=name)

    @classmethod
    def list_categories(cls, owner) -> models.QuerySet:
        return Category.objects.filter(owner=owner).order_by("name")

    @classmethod
    def update_category(cls, category: Category, name: str) -> Category:
        category.name = name
        category.save(update_fields=["name"])
        return category

    @classmethod
    def delete_category(cls, category: Category) -> None:
        category.delete()


class WalletBalanceService:
    @classmethod
    def get_balance(cls, wallet: Wallet) -> Decimal:
        credits = Transaction.objects.filter(
            wallet=wallet,
            type__in=[Transaction.Type.INCOME, Transaction.Type.TRANSFER_IN],
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

        debits = Transaction.objects.filter(
            wallet=wallet,
            type__in=[Transaction.Type.EXPENSE, Transaction.Type.TRANSFER_OUT],
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

        return credits - debits


class WalletAnalyticsService:
    @classmethod
    def get_user_total_balance(cls, user) -> Decimal:
        wallets = Wallet.objects.filter(owner=user)
        total = Decimal("0.00")
        for wallet in wallets:
            total += WalletBalanceService.get_balance(wallet)
        return total

class WalletTransactionService:
    @classmethod
    def record_income(
        cls,
        wallet: Wallet,
        amount: Decimal,
        description: str | None,
        date,
        category: Category | None = None,
    ) -> Transaction:
        return Transaction.objects.create(
            type=Transaction.Type.INCOME,
            wallet=wallet,
            amount=amount,
            description=description,
            date=date,
            category=category,
        )

    @classmethod
    def record_expense(
        cls,
        wallet: Wallet,
        balance: Decimal,
        amount: Decimal,
        description: str | None,
        date,
        category: Category | None = None,
    ) -> Transaction:
        if not wallet.can_be_negative:
            if amount > balance:
                raise ValidationError(
                    f"Insufficient funds. Balance: {balance}, expense: {amount}"
                )

        return Transaction.objects.create(
            type=Transaction.Type.EXPENSE,
            wallet=wallet,
            amount=amount,
            description=description,
            date=date,
            category=category,
        )

    @classmethod
    def get_transaction(cls, uuid) -> Transaction:
        return Transaction.objects.get(uuid=uuid)

    @classmethod
    def list_transactions(
        cls,
        wallet: Wallet,
        type: str | None = None,
        date_from=None,
        date_to=None,
        category: Category | None = None,
    ) -> models.QuerySet:
        qs = Transaction.objects.filter(wallet=wallet).order_by("-date", "-uuid")

        if type:
            qs = qs.filter(type=type)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if category:
            qs = qs.filter(category=category)

        return qs

    @classmethod
    def delete_transaction(cls, transaction: Transaction) -> None:
        if transaction.transfer_group_id:
            raise ValidationError(
                "Cannot delete a transfer transaction directly. "
                "Use TransferService.reverse_transfer to undo the entire transfer."
            )

        if transaction.type in (
            Transaction.Type.INCOME,
            Transaction.Type.TRANSFER_IN,
        ):
            balance = WalletBalanceService.get_balance(transaction.wallet)
            new_balance = balance - transaction.amount
            if not transaction.wallet.can_be_negative and new_balance < 0:
                raise ValidationError(
                    f"Cannot delete this {transaction.type}. "
                    f"New balance would be {new_balance}."
                )

        transaction.delete()

    @classmethod
    def update_transaction(
        cls,
        transaction: Transaction,
        amount: Decimal | None = None,
        description: str | None = None,
        date=None,
        category: Category | None = None,
    ) -> Transaction:
        if transaction.transfer_group_id:
            raise ValidationError(
                "Cannot edit a transfer transaction. "
                "Reverse the transfer and create a new one instead."
            )

        if amount is not None and amount != transaction.amount:
            if transaction.type in (
                Transaction.Type.EXPENSE,
                Transaction.Type.TRANSFER_OUT,
            ):
                balance_without = (
                    WalletBalanceService.get_balance(transaction.wallet)
                    + transaction.amount
                )
                if not transaction.wallet.can_be_negative and amount > balance_without:
                    raise ValidationError(
                        f"Insufficient funds. Balance without this transaction: "
                        f"{balance_without}, new amount: {amount}"
                    )

        if amount is not None:
            transaction.amount = amount
        if description is not None:
            transaction.description = description
        if date is not None:
            transaction.date = date
        if category is not None:
            transaction.category = category

        transaction.save(update_fields=["amount", "description", "date", "category"])
        return transaction


class TransferService:
    @classmethod
    def transfer(
        cls,
        from_wallet: Wallet,
        to_wallet: Wallet,
        balance: Decimal,
        amount: Decimal,
        description: str | None,
        date,
        category: Category | None = None,
    ) -> TransferGroup:
        if from_wallet == to_wallet:
            raise ValidationError("Cannot transfer to the same wallet")

        if not from_wallet.can_be_negative:
            if amount > balance:
                raise ValidationError(
                    f"Insufficient funds in '{from_wallet.name}'. Balance: {balance}, transfer: {amount}"
                )

        with db_transaction.atomic():
            group = TransferGroup.objects.create()
            Transaction.objects.create(
                type=Transaction.Type.TRANSFER_OUT,
                wallet=from_wallet,
                amount=amount,
                description=description,
                date=date,
                transfer_group=group,
                category=category,
            )
            Transaction.objects.create(
                type=Transaction.Type.TRANSFER_IN,
                wallet=to_wallet,
                amount=amount,
                description=description,
                date=date,
                transfer_group=group,
                category=category,
            )

        return group

    @classmethod
    def reverse_transfer(cls, transfer_group: TransferGroup) -> None:
        transactions = list(transfer_group.transactions.select_related("wallet"))

        if not transactions:
            raise ValidationError("Transfer group has no transactions")

        for transaction in transactions:
            if transaction.type == Transaction.Type.TRANSFER_IN:
                balance = WalletBalanceService.get_balance(transaction.wallet)
                new_balance = balance - transaction.amount
                if not transaction.wallet.can_be_negative and new_balance < 0:
                    raise ValidationError(
                        f"Cannot reverse transfer. "
                        f"'{transaction.wallet.name}' would have a negative balance of {new_balance}."
                    )

        with db_transaction.atomic():
            for transaction in transactions:
                transaction.delete()
            transfer_group.delete()


class WalletService:
    @classmethod
    def create_wallet(cls, owner, name, can_be_negative=False) -> Wallet:
        return Wallet.objects.create(
            owner=owner, name=name, can_be_negative=can_be_negative
        )

    @classmethod
    def list_wallets(cls, owner) -> models.QuerySet:
        return Wallet.objects.filter(owner=owner)

    @classmethod
    def update_wallet(
        cls,
        wallet: Wallet,
        name: str | None = None,
        can_be_negative: bool | None = None,
    ) -> Wallet:
        if name is not None:
            wallet.name = name
        if can_be_negative is not None:
            wallet.can_be_negative = can_be_negative
        wallet.save(update_fields=["name", "can_be_negative"])
        return wallet

    @classmethod
    def delete_wallet(cls, wallet: Wallet) -> None:
        balance = WalletBalanceService.get_balance(wallet)
        if balance != 0:
            raise ValidationError(
                f"Cannot delete wallet with non-zero balance ({balance}). "
                "Move the money elsewhere first."
            )
        wallet.delete()
