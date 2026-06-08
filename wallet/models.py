from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models

from wimm.base_models import BaseModel

User = get_user_model()


class Wallet(BaseModel):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wallets")
    name = models.CharField(max_length=255)
    can_be_negative = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Category(BaseModel):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], name="unique_category_per_user"
            )
        ]

    def __str__(self):
        return self.name


class TransferGroup(BaseModel):
    pass


class Transaction(BaseModel):
    class Type(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"
        TRANSFER_OUT = "transfer_out", "Transfer Out"
        TRANSFER_IN = "transfer_in", "Transfer In"

    type = models.CharField(max_length=20, choices=Type.choices)
    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="transactions"
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    description = models.CharField(max_length=500, blank=True)
    date = models.DateField()
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    transfer_group = models.ForeignKey(
        TransferGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )

    @property
    def transfer_counterpart(self):
        if not self.transfer_group_id:
            return None
        counterpart = self.transfer_group.transactions.exclude(uuid=self.uuid).first()
        return counterpart.wallet if counterpart else None
