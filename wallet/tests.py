from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import CustomUser
from wallet.models import Category, Transaction, TransferGroup, Wallet
from wallet.services import (
    CategoryService,
    TransferService,
    WalletAnalyticsService,
    WalletBalanceService,
    WalletService,
    WalletTransactionService,
)


class CategoryServiceTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="pass"
        )
        self.other = CustomUser.objects.create_user(
            username="other", password="pass"
        )

    def test_create_category(self):
        cat = CategoryService.create_category(owner=self.user, name="Food")
        self.assertEqual(cat.name, "Food")
        self.assertEqual(cat.owner, self.user)

    def test_list_categories(self):
        CategoryService.create_category(owner=self.user, name="A")
        CategoryService.create_category(owner=self.user, name="B")
        CategoryService.create_category(owner=self.other, name="C")
        cats = CategoryService.list_categories(owner=self.user)
        self.assertEqual(list(cats.values_list("name", flat=True)), ["A", "B"])

    def test_update_category(self):
        cat = CategoryService.create_category(owner=self.user, name="Old")
        CategoryService.update_category(cat, name="Renamed")
        cat.refresh_from_db()
        self.assertEqual(cat.name, "Renamed")

    def test_delete_category(self):
        cat = CategoryService.create_category(owner=self.user, name="Temp")
        CategoryService.delete_category(cat)
        self.assertFalse(Category.objects.filter(uuid=cat.uuid).exists())

    def test_unique_category_per_user(self):
        CategoryService.create_category(owner=self.user, name="Food")
        with self.assertRaises(Exception):
            CategoryService.create_category(owner=self.user, name="Food")

    def test_same_name_different_users(self):
        CategoryService.create_category(owner=self.user, name="Food")
        cat = CategoryService.create_category(owner=self.other, name="Food")
        self.assertIsNotNone(cat.uuid)


class WalletServiceTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="pass"
        )

    def test_create_wallet(self):
        wallet = WalletService.create_wallet(
            owner=self.user, name="My Wallet"
        )
        self.assertEqual(wallet.name, "My Wallet")
        self.assertEqual(wallet.owner, self.user)
        self.assertFalse(wallet.can_be_negative)

    def test_create_wallet_can_be_negative(self):
        wallet = WalletService.create_wallet(
            owner=self.user, name="Credit", can_be_negative=True
        )
        self.assertTrue(wallet.can_be_negative)

    def test_list_wallets(self):
        WalletService.create_wallet(owner=self.user, name="A")
        WalletService.create_wallet(owner=self.user, name="B")
        wallets = WalletService.list_wallets(owner=self.user)
        self.assertEqual(wallets.count(), 2)

    def test_list_wallets_other_user(self):
        other = CustomUser.objects.create_user(
            username="other", password="pass"
        )
        WalletService.create_wallet(owner=self.user, name="Mine")
        wallets = WalletService.list_wallets(owner=other)
        self.assertEqual(wallets.count(), 0)

    def test_update_wallet_name(self):
        wallet = WalletService.create_wallet(owner=self.user, name="Old")
        WalletService.update_wallet(wallet, name="New")
        wallet.refresh_from_db()
        self.assertEqual(wallet.name, "New")

    def test_update_wallet_can_be_negative(self):
        wallet = WalletService.create_wallet(owner=self.user, name="W")
        WalletService.update_wallet(wallet, can_be_negative=True)
        wallet.refresh_from_db()
        self.assertTrue(wallet.can_be_negative)

    def test_update_wallet_partial(self):
        wallet = WalletService.create_wallet(owner=self.user, name="W")
        WalletService.update_wallet(wallet, name="Updated")
        wallet.refresh_from_db()
        self.assertEqual(wallet.name, "Updated")
        self.assertFalse(wallet.can_be_negative)

    def test_delete_wallet_zero_balance(self):
        wallet = WalletService.create_wallet(owner=self.user, name="W")
        WalletService.delete_wallet(wallet)
        self.assertFalse(Wallet.objects.filter(uuid=wallet.uuid).exists())

    def test_delete_wallet_non_zero_balance(self):
        wallet = WalletService.create_wallet(owner=self.user, name="W")
        WalletTransactionService.record_income(
            wallet=wallet, amount=Decimal("100"), description="", date=date.today()
        )
        with self.assertRaises(ValidationError):
            WalletService.delete_wallet(wallet)


class WalletBalanceServiceTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="pass"
        )
        self.wallet = WalletService.create_wallet(owner=self.user, name="W")

    def test_get_balance_empty(self):
        self.assertEqual(
            WalletBalanceService.get_balance(self.wallet), Decimal("0.00")
        )

    def test_get_balance_after_income(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        self.assertEqual(
            WalletBalanceService.get_balance(self.wallet), Decimal("100")
        )

    def test_get_balance_after_expense(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("100"),
            amount=Decimal("30"),
            description="",
            date=date.today(),
        )
        self.assertEqual(
            WalletBalanceService.get_balance(self.wallet), Decimal("70")
        )

    def test_get_balance_after_transfer_in(self):
        other = WalletService.create_wallet(owner=self.user, name="Other")
        WalletTransactionService.record_income(
            wallet=other,
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        TransferService.transfer(
            from_wallet=other,
            to_wallet=self.wallet,
            balance=Decimal("50"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        self.assertEqual(
            WalletBalanceService.get_balance(self.wallet), Decimal("50")
        )

    def test_get_balance_after_transfer_out(self):
        other = WalletService.create_wallet(owner=self.user, name="Other")
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        TransferService.transfer(
            from_wallet=self.wallet,
            to_wallet=other,
            balance=Decimal("100"),
            amount=Decimal("40"),
            description="",
            date=date.today(),
        )
        self.assertEqual(
            WalletBalanceService.get_balance(self.wallet), Decimal("60")
        )

    def test_get_balance_mixed(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("200"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("200"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        other = WalletService.create_wallet(owner=self.user, name="Other")
        TransferService.transfer(
            from_wallet=self.wallet,
            to_wallet=other,
            balance=Decimal("150"),
            amount=Decimal("30"),
            description="",
            date=date.today(),
        )
        self.assertEqual(
            WalletBalanceService.get_balance(self.wallet), Decimal("120")
        )

    def test_get_user_total_balance(self):
        other = WalletService.create_wallet(owner=self.user, name="Other")
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.record_income(
            wallet=other,
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        total = WalletAnalyticsService.get_user_total_balance(self.user)
        self.assertEqual(total, Decimal("150"))

    def test_get_user_total_balance_no_wallets(self):
        new_user = CustomUser.objects.create_user(
            username="newuser", password="pass"
        )
        total = WalletAnalyticsService.get_user_total_balance(new_user)
        self.assertEqual(total, Decimal("0.00"))

    def test_get_user_total_balance_other_user_isolated(self):
        other_user = CustomUser.objects.create_user(
            username="other", password="pass"
        )
        other_wallet = WalletService.create_wallet(
            owner=other_user, name="Other"
        )
        WalletTransactionService.record_income(
            wallet=other_wallet,
            amount=Decimal("999"),
            description="",
            date=date.today(),
        )
        total = WalletAnalyticsService.get_user_total_balance(self.user)
        self.assertEqual(total, Decimal("0.00"))

class WalletTransactionServiceTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="pass"
        )
        self.wallet = WalletService.create_wallet(owner=self.user, name="W")

    def test_record_income(self):
        tx = WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="Salary",
            date=date(2025, 1, 15),
        )
        self.assertEqual(tx.type, Transaction.Type.INCOME)
        self.assertEqual(tx.amount, Decimal("100"))
        self.assertEqual(tx.description, "Salary")
        self.assertEqual(tx.date, date(2025, 1, 15))
        self.assertEqual(tx.wallet, self.wallet)

    def test_record_expense(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        tx = WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("100"),
            amount=Decimal("30"),
            description="Coffee",
            date=date(2025, 2, 10),
        )
        self.assertEqual(tx.type, Transaction.Type.EXPENSE)
        self.assertEqual(tx.amount, Decimal("30"))
        self.assertEqual(tx.description, "Coffee")
        self.assertEqual(tx.date, date(2025, 2, 10))

    def test_record_expense_insufficient_funds(self):
        with self.assertRaises(ValidationError):
            WalletTransactionService.record_expense(
                wallet=self.wallet,
                balance=Decimal("0"),
                amount=Decimal("10"),
                description="",
                date=date.today(),
            )

    def test_record_expense_can_be_negative(self):
        credit_wallet = WalletService.create_wallet(
            owner=self.user, name="Credit", can_be_negative=True
        )
        tx = WalletTransactionService.record_expense(
            wallet=credit_wallet,
            balance=Decimal("0"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        self.assertEqual(tx.amount, Decimal("50"))

    def test_get_transaction(self):
        created = WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("10"),
            description="",
            date=date.today(),
        )
        fetched = WalletTransactionService.get_transaction(created.uuid)
        self.assertEqual(fetched.uuid, created.uuid)

    def test_get_transaction_not_found(self):
        with self.assertRaises(Transaction.DoesNotExist):
            WalletTransactionService.get_transaction(
                "00000000-0000-0000-0000-000000000000"
            )

    def test_list_transactions(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("10"),
            description="",
            date=date(2025, 1, 1),
        )
        WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("10"),
            amount=Decimal("5"),
            description="",
            date=date(2025, 1, 2),
        )
        qs = WalletTransactionService.list_transactions(wallet=self.wallet)
        self.assertEqual(qs.count(), 2)

    def test_list_transactions_filter_type(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("10"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("10"),
            amount=Decimal("5"),
            description="",
            date=date.today(),
        )
        qs = WalletTransactionService.list_transactions(
            wallet=self.wallet, type=Transaction.Type.INCOME
        )
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().type, Transaction.Type.INCOME)

    def test_list_transactions_filter_date_range(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("10"),
            description="",
            date=date(2025, 1, 1),
        )
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("20"),
            description="",
            date=date(2025, 2, 1),
        )
        qs = WalletTransactionService.list_transactions(
            wallet=self.wallet,
            date_from=date(2025, 1, 15),
            date_to=date(2025, 2, 15),
        )
        self.assertEqual(qs.count(), 1)

    def test_delete_income_transaction(self):
        tx = WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.delete_transaction(tx)
        self.assertFalse(
            Transaction.objects.filter(uuid=tx.uuid).exists()
        )

    def test_delete_income_would_go_negative(self):
        tx = WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("100"),
            amount=Decimal("80"),
            description="",
            date=date.today(),
        )
        with self.assertRaises(ValidationError):
            WalletTransactionService.delete_transaction(tx)

    def test_delete_income_can_be_negative(self):
        credit_wallet = WalletService.create_wallet(
            owner=self.user, name="Credit", can_be_negative=True
        )
        tx = WalletTransactionService.record_income(
            wallet=credit_wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.record_expense(
            wallet=credit_wallet,
            balance=Decimal("100"),
            amount=Decimal("80"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.delete_transaction(tx)
        self.assertFalse(
            Transaction.objects.filter(uuid=tx.uuid).exists()
        )

    def test_delete_expense_transaction(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        tx = WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("100"),
            amount=Decimal("30"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.delete_transaction(tx)
        self.assertFalse(
            Transaction.objects.filter(uuid=tx.uuid).exists()
        )

    def test_delete_transfer_transaction_raises_error(self):
        other = WalletService.create_wallet(owner=self.user, name="Other")
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        group = TransferService.transfer(
            from_wallet=self.wallet,
            to_wallet=other,
            balance=Decimal("100"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        tx = group.transactions.filter(
            type=Transaction.Type.TRANSFER_OUT
        ).first()
        with self.assertRaises(ValidationError):
            WalletTransactionService.delete_transaction(tx)

    def test_record_income_with_category(self):
        cat = CategoryService.create_category(owner=self.user, name="Salary")
        tx = WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
            category=cat,
        )
        self.assertEqual(tx.category, cat)

    def test_record_expense_with_category(self):
        cat = CategoryService.create_category(owner=self.user, name="Food")
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        tx = WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("100"),
            amount=Decimal("30"),
            description="",
            date=date.today(),
            category=cat,
        )
        self.assertEqual(tx.category, cat)

    def test_list_transactions_filter_category(self):
        food = CategoryService.create_category(owner=self.user, name="Food")
        transport = CategoryService.create_category(
            owner=self.user, name="Transport"
        )
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("100"),
            amount=Decimal("20"),
            description="",
            date=date.today(),
            category=food,
        )
        WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("80"),
            amount=Decimal("10"),
            description="",
            date=date.today(),
            category=transport,
        )
        qs = WalletTransactionService.list_transactions(
            wallet=self.wallet, category=food
        )
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().category, food)

    def test_delete_category_sets_null_on_transactions(self):
        cat = CategoryService.create_category(owner=self.user, name="Food")
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
            category=cat,
        )
        CategoryService.delete_category(cat)
        tx = Transaction.objects.get(wallet=self.wallet)
        self.assertIsNone(tx.category)

    def test_update_transaction_description(self):
        tx = WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="Old",
            date=date(2025, 1, 1),
        )
        WalletTransactionService.update_transaction(
            tx, description="Updated"
        )
        tx.refresh_from_db()
        self.assertEqual(tx.description, "Updated")
        self.assertEqual(tx.amount, Decimal("100"))

    def test_update_transaction_amount(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("200"),
            description="",
            date=date.today(),
        )
        tx = WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("200"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.update_transaction(tx, amount=Decimal("30"))
        tx.refresh_from_db()
        self.assertEqual(tx.amount, Decimal("30"))

    def test_update_transaction_amount_insufficient_funds(self):
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        tx = WalletTransactionService.record_expense(
            wallet=self.wallet,
            balance=Decimal("100"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        with self.assertRaises(ValidationError):
            WalletTransactionService.update_transaction(
                tx, amount=Decimal("200")
            )

    def test_update_transaction_date_and_category(self):
        cat = CategoryService.create_category(owner=self.user, name="Food")
        tx = WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date(2025, 1, 1),
        )
        WalletTransactionService.update_transaction(
            tx, date=date(2025, 6, 1), category=cat
        )
        tx.refresh_from_db()
        self.assertEqual(tx.date, date(2025, 6, 1))
        self.assertEqual(tx.category, cat)

    def test_update_transfer_transaction_raises_error(self):
        other = WalletService.create_wallet(owner=self.user, name="Other")
        WalletTransactionService.record_income(
            wallet=self.wallet,
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        group = TransferService.transfer(
            from_wallet=self.wallet,
            to_wallet=other,
            balance=Decimal("100"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        tx = group.transactions.first()
        with self.assertRaises(ValidationError):
            WalletTransactionService.update_transaction(
                tx, description="Nope"
            )


class TransferServiceTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="pass"
        )
        self.from_wallet = WalletService.create_wallet(
            owner=self.user, name="Source"
        )
        self.to_wallet = WalletService.create_wallet(
            owner=self.user, name="Dest"
        )
        WalletTransactionService.record_income(
            wallet=self.from_wallet,
            amount=Decimal("200"),
            description="",
            date=date.today(),
        )

    def test_transfer(self):
        group = TransferService.transfer(
            from_wallet=self.from_wallet,
            to_wallet=self.to_wallet,
            balance=Decimal("200"),
            amount=Decimal("50"),
            description="Gift",
            date=date(2025, 3, 1),
        )
        self.assertIsNotNone(group.uuid)
        transactions = group.transactions.all()
        self.assertEqual(transactions.count(), 2)

        out_tx = transactions.get(type=Transaction.Type.TRANSFER_OUT)
        self.assertEqual(out_tx.wallet, self.from_wallet)
        self.assertEqual(out_tx.amount, Decimal("50"))
        self.assertEqual(out_tx.description, "Gift")
        self.assertEqual(out_tx.date, date(2025, 3, 1))

        in_tx = transactions.get(type=Transaction.Type.TRANSFER_IN)
        self.assertEqual(in_tx.wallet, self.to_wallet)
        self.assertEqual(in_tx.amount, Decimal("50"))

    def test_transfer_same_wallet(self):
        with self.assertRaises(ValidationError):
            TransferService.transfer(
                from_wallet=self.from_wallet,
                to_wallet=self.from_wallet,
                balance=Decimal("200"),
                amount=Decimal("10"),
                description="",
                date=date.today(),
            )

    def test_transfer_insufficient_funds(self):
        with self.assertRaises(ValidationError):
            TransferService.transfer(
                from_wallet=self.from_wallet,
                to_wallet=self.to_wallet,
                balance=Decimal("200"),
                amount=Decimal("300"),
                description="",
                date=date.today(),
            )

    def test_transfer_sets_description(self):
        group = TransferService.transfer(
            from_wallet=self.from_wallet,
            to_wallet=self.to_wallet,
            balance=Decimal("200"),
            amount=Decimal("50"),
            description="Gift",
            date=date.today(),
        )
        for tx in group.transactions.all():
            self.assertEqual(tx.description, "Gift")

    def test_transfer_can_be_negative(self):
        credit_wallet = WalletService.create_wallet(
            owner=self.user, name="Credit", can_be_negative=True
        )
        group = TransferService.transfer(
            from_wallet=credit_wallet,
            to_wallet=self.to_wallet,
            balance=Decimal("0"),
            amount=Decimal("100"),
            description="",
            date=date.today(),
        )
        self.assertEqual(group.transactions.count(), 2)

    def test_reverse_transfer(self):
        group = TransferService.transfer(
            from_wallet=self.from_wallet,
            to_wallet=self.to_wallet,
            balance=Decimal("200"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        group_uuid = group.uuid
        TransferService.reverse_transfer(group)
        self.assertFalse(
            TransferGroup.objects.filter(uuid=group_uuid).exists()
        )
        self.assertEqual(
            Transaction.objects.filter(transfer_group_id=group_uuid).count(), 0
        )

    def test_reverse_transfer_destination_would_go_negative(self):
        group = TransferService.transfer(
            from_wallet=self.from_wallet,
            to_wallet=self.to_wallet,
            balance=Decimal("200"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        WalletTransactionService.record_expense(
            wallet=self.to_wallet,
            balance=Decimal("50"),
            amount=Decimal("50"),
            description="",
            date=date.today(),
        )
        with self.assertRaises(ValidationError):
            TransferService.reverse_transfer(group)

    def test_reverse_transfer_empty_group(self):
        group = TransferGroup.objects.create()
        with self.assertRaises(ValidationError):
            TransferService.reverse_transfer(group)
