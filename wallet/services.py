from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction as db_transaction

from .models import Transaction, TransferGroup, Wallet


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


class WalletTransactionService:
    @classmethod
    def record_income(
        cls, wallet: Wallet, amount: Decimal, description: str | None, date
    ) -> Transaction:
        return Transaction.objects.create(
            type=Transaction.Type.INCOME,
            wallet=wallet,
            amount=amount,
            description=description,
            date=date,
        )

    @classmethod
    def record_expense(
        cls,
        wallet: Wallet,
        balance: Decimal,
        amount: Decimal,
        description: str | None,
        date,
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
        )


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
            )
            Transaction.objects.create(
                type=Transaction.Type.TRANSFER_IN,
                wallet=to_wallet,
                amount=amount,
                description=description,
                date=date,
                transfer_group=group,
            )

        return group
