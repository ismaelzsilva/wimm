import csv
from datetime import date
from decimal import Decimal

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from wallet.models import Category, Transaction, Wallet
from wallet.services import (
    CategoryService,
    TransferService,
    WalletAnalyticsService,
    WalletBalanceService,
    WalletService,
    WalletTransactionService,
)


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def login_view(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse("dashboard"))

    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            response = HttpResponse()
            response["HX-Redirect"] = reverse("dashboard")
            return response
        return render(
            request, "wallet/auth/login.html", {"error": "Invalid credentials"}
        )

    return render(request, "wallet/auth/login.html")


def logout_view(request):
    logout(request)
    response = HttpResponse()
    response["HX-Redirect"] = reverse("login")
    return response


def signup_view(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse("dashboard"))

    if request.method == "POST":
        from accounts.models import CustomUser

        username = request.POST["username"]
        password = request.POST["password"]
        password_confirm = request.POST["password_confirm"]

        if password != password_confirm:
            return render(
                request, "wallet/auth/signup.html", {"error": "Passwords do not match"}
            )

        if CustomUser.objects.filter(username=username).exists():
            return render(
                request, "wallet/auth/signup.html", {"error": "Username already taken"}
            )

        user = CustomUser.objects.create_user(username=username, password=password)
        login(request, user)
        response = HttpResponse()
        response["HX-Redirect"] = reverse("dashboard")
        return response

    return render(request, "wallet/auth/signup.html")


@login_required
def dashboard(request):
    wallets = WalletService.list_wallets(request.user)
    wallet_balances = [(w, WalletBalanceService.get_balance(w)) for w in wallets]
    total_balance = WalletAnalyticsService.get_user_total_balance(request.user)
    return render(
        request,
        "wallet/dashboard.html",
        {
            "wallet_balances": wallet_balances,
            "total_balance": total_balance,
        },
    )


@login_required
def wallet_create(request):
    if request.method == "POST":
        name = request.POST["name"]
        can_be_negative = request.POST.get("can_be_negative") == "on"
        WalletService.create_wallet(
            owner=request.user, name=name, can_be_negative=can_be_negative
        )
        response = HttpResponse()
        response["HX-Redirect"] = reverse("dashboard")
        return response

    return render(request, "wallet/wallet/_form.html")


@login_required
def wallet_detail(request, uuid):
    wallet = get_object_or_404(Wallet, uuid=uuid, owner=request.user)
    balance = WalletBalanceService.get_balance(wallet)
    tx_type = request.GET.get("type")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    category_uuid = request.GET.get("category")

    category = None
    if category_uuid:
        category = get_object_or_404(Category, uuid=category_uuid, owner=request.user)

    transactions = WalletTransactionService.list_transactions(
        wallet=wallet,
        type=tx_type,
        date_from=date_from or None,
        date_to=date_to or None,
        category=category,
    )

    expense_breakdown = WalletTransactionService.get_category_breakdown(
        wallet=wallet,
        type=tx_type,
        date_from=date_from or None,
        date_to=date_to or None,
        category=category,
    )

    income_breakdown = WalletTransactionService.get_category_breakdown(
        wallet=wallet,
        types=[Transaction.Type.INCOME, Transaction.Type.TRANSFER_IN],
        type=tx_type,
        date_from=date_from or None,
        date_to=date_to or None,
        category=category,
    )

    categories = CategoryService.list_categories(request.user)
    other_wallets = WalletService.list_wallets(request.user).exclude(uuid=wallet.uuid)

    if _is_htmx(request):
        return render(
            request,
            "wallet/transaction/_list.html",
            {
                "wallet": wallet,
                "transactions": transactions,
                "categories": categories,
                "balance": balance,
                "expense_breakdown": expense_breakdown,
                "income_breakdown": income_breakdown,
            },
        )

    return render(
        request,
        "wallet/wallet/detail.html",
        {
            "wallet": wallet,
            "balance": balance,
            "transactions": transactions,
            "categories": categories,
            "other_wallets": other_wallets,
            "expense_breakdown": expense_breakdown,
            "income_breakdown": income_breakdown,
        },
    )


@login_required
def wallet_update(request, uuid):
    wallet = get_object_or_404(Wallet, uuid=uuid, owner=request.user)

    if request.method == "POST":
        name = request.POST["name"]
        can_be_negative = request.POST.get("can_be_negative") == "on"
        WalletService.update_wallet(
            wallet=wallet, name=name, can_be_negative=can_be_negative
        )
        response = HttpResponse()
        response["HX-Redirect"] = reverse("dashboard")
        return response

    return render(request, "wallet/wallet/_form.html", {"wallet": wallet})


@login_required
def wallet_delete(request, uuid):
    wallet = get_object_or_404(Wallet, uuid=uuid, owner=request.user)

    if request.method == "POST":
        try:
            WalletService.delete_wallet(wallet)
        except Exception as e:
            return render(
                request,
                "wallet/wallet/_confirm_delete.html",
                {"wallet": wallet, "error": str(e)},
            )
        response = HttpResponse()
        response["HX-Redirect"] = reverse("dashboard")
        return response

    return render(request, "wallet/wallet/_confirm_delete.html", {"wallet": wallet})


@login_required
def transaction_create(request, wallet_uuid):
    wallet = get_object_or_404(Wallet, uuid=wallet_uuid, owner=request.user)
    categories = CategoryService.list_categories(request.user)
    tx_type = request.GET.get("type", Transaction.Type.EXPENSE)

    if request.method == "POST":
        amount = Decimal(request.POST["amount"])
        description = request.POST.get("description", "")
        tx_date = request.POST.get("date", date.today())
        category_uuid = request.POST.get("category")
        category = (
            get_object_or_404(Category, uuid=category_uuid, owner=request.user)
            if category_uuid
            else None
        )
        tx_type = request.POST["type"]

        balance = WalletBalanceService.get_balance(wallet)

        try:
            if tx_type == Transaction.Type.INCOME:
                WalletTransactionService.record_income(
                    wallet=wallet,
                    amount=amount,
                    description=description,
                    date=tx_date,
                    category=category,
                )
            else:
                WalletTransactionService.record_expense(
                    wallet=wallet,
                    balance=balance,
                    amount=amount,
                    description=description,
                    date=tx_date,
                    category=category,
                )
        except Exception as e:
            return render(
                request,
                "wallet/transaction/_form.html",
                {
                    "wallet": wallet,
                    "categories": categories,
                    "type": tx_type,
                    "error": str(e),
                },
            )

        response = HttpResponse()
        response["HX-Redirect"] = reverse("wallet_detail", args=[wallet.uuid])
        return response

    return render(
        request,
        "wallet/transaction/_form.html",
        {
            "wallet": wallet,
            "categories": categories,
            "type": tx_type,
        },
    )


@login_required
def transaction_update(request, wallet_uuid, uuid):
    wallet = get_object_or_404(Wallet, uuid=wallet_uuid, owner=request.user)
    transaction = get_object_or_404(Transaction, uuid=uuid, wallet=wallet)
    categories = CategoryService.list_categories(request.user)

    if request.method == "POST":
        amount = Decimal(request.POST.get("amount"))
        description = request.POST.get("description", "")
        tx_date = request.POST.get("date")
        category_uuid = request.POST.get("category")
        category = (
            get_object_or_404(Category, uuid=category_uuid, owner=request.user)
            if category_uuid
            else None
        )

        try:
            WalletTransactionService.update_transaction(
                transaction=transaction,
                amount=amount,
                description=description,
                date=tx_date,
                category=category,
            )
        except Exception as e:
            return render(
                request,
                "wallet/transaction/_form.html",
                {
                    "wallet": wallet,
                    "categories": categories,
                    "transaction": transaction,
                    "error": str(e),
                },
            )

        response = HttpResponse()
        response["HX-Redirect"] = reverse("wallet_detail", args=[wallet.uuid])
        return response

    return render(
        request,
        "wallet/transaction/_form.html",
        {
            "wallet": wallet,
            "categories": categories,
            "transaction": transaction,
        },
    )


@login_required
def transaction_delete(request, wallet_uuid, uuid):
    wallet = get_object_or_404(Wallet, uuid=wallet_uuid, owner=request.user)
    transaction = get_object_or_404(Transaction, uuid=uuid, wallet=wallet)

    if request.method == "POST":
        try:
            WalletTransactionService.delete_transaction(transaction)
        except Exception as e:
            return render(
                request,
                "wallet/transaction/_confirm_delete.html",
                {"wallet": wallet, "transaction": transaction, "error": str(e)},
            )
        response = HttpResponse()
        response["HX-Redirect"] = reverse("wallet_detail", args=[wallet.uuid])
        return response

    return render(
        request,
        "wallet/transaction/_confirm_delete.html",
        {"wallet": wallet, "transaction": transaction},
    )


@login_required
def wallet_transfer_fast(request, uuid):
    wallet = get_object_or_404(Wallet, uuid=uuid, owner=request.user)
    other_wallets = WalletService.list_wallets(request.user).exclude(uuid=wallet.uuid)

    if request.method == "POST":
        to_wallet_uuid = request.POST.get("to_wallet")
        amount = Decimal(request.POST["amount"])
        description = request.POST.get("description", "")
        tx_date = request.POST.get("date", date.today())

        to_wallet = get_object_or_404(Wallet, uuid=to_wallet_uuid, owner=request.user)
        balance = WalletBalanceService.get_balance(wallet)

        try:
            TransferService.transfer(
                from_wallet=wallet,
                to_wallet=to_wallet,
                balance=balance,
                amount=amount,
                description=description,
                date=tx_date,
            )
        except Exception as e:
            transactions = WalletTransactionService.list_transactions(wallet)
            balance = WalletBalanceService.get_balance(wallet)
            return render(
                request,
                "wallet/wallet/_content.html",
                {
                    "wallet": wallet,
                    "other_wallets": other_wallets,
                    "transactions": transactions,
                    "balance": balance,
                    "error": str(e),
                },
            )

        transactions = WalletTransactionService.list_transactions(wallet)
        balance = WalletBalanceService.get_balance(wallet)
        return render(
            request,
            "wallet/wallet/_content.html",
            {
                "wallet": wallet,
                "other_wallets": other_wallets,
                "transactions": transactions,
                "balance": balance,
            },
        )

    return render(
        request,
        "wallet/transfer/_fast_form.html",
        {"wallet": wallet, "other_wallets": other_wallets},
    )


@login_required
def transfer_update(request, wallet_uuid, uuid):
    wallet = get_object_or_404(Wallet, uuid=wallet_uuid, owner=request.user)
    transaction = get_object_or_404(Transaction, uuid=uuid, wallet=wallet)
    transfer_group = transaction.transfer_group

    if not transfer_group:
        return HttpResponse(status=404)

    if request.method == "POST":
        amount = request.POST.get("amount")
        description = request.POST.get("description", "")
        tx_date = request.POST.get("date")

        try:
            TransferService.update_transfer(
                transfer_group=transfer_group,
                amount=Decimal(amount) if amount else None,
                description=description,
                date=tx_date or None,
            )
        except Exception as e:
            return render(
                request,
                "wallet/transfer/_edit_form.html",
                {
                    "wallet": wallet,
                    "transaction": transaction,
                    "error": str(e),
                },
            )

        response = HttpResponse()
        response["HX-Redirect"] = reverse("wallet_detail", args=[wallet.uuid])
        return response

    return render(
        request,
        "wallet/transfer/_edit_form.html",
        {"wallet": wallet, "transaction": transaction},
    )


@login_required
def transfer_delete(request, wallet_uuid, uuid):
    wallet = get_object_or_404(Wallet, uuid=wallet_uuid, owner=request.user)
    transaction = get_object_or_404(Transaction, uuid=uuid, wallet=wallet)
    transfer_group = transaction.transfer_group

    if not transfer_group:
        return HttpResponse(status=404)

    if request.method == "POST":
        try:
            TransferService.reverse_transfer(transfer_group)
        except Exception as e:
            return render(
                request,
                "wallet/transfer/_confirm_delete.html",
                {"wallet": wallet, "transaction": transaction, "error": str(e)},
            )
        response = HttpResponse()
        response["HX-Redirect"] = reverse("wallet_detail", args=[wallet.uuid])
        return response

    return render(
        request,
        "wallet/transfer/_confirm_delete.html",
        {"wallet": wallet, "transaction": transaction},
    )


@login_required
def category_list(request):
    categories = CategoryService.list_categories(request.user)
    return render(request, "wallet/category/list.html", {"categories": categories})


@login_required
def category_create(request):
    if request.method == "POST":
        name = request.POST["name"]
        try:
            CategoryService.create_category(owner=request.user, name=name)
        except Exception as e:
            return render(
                request,
                "wallet/category/_form.html",
                {"error": str(e)},
            )
        response = HttpResponse()
        response["HX-Redirect"] = reverse("category_list")
        return response

    return render(request, "wallet/category/_form.html")


@login_required
def category_update(request, uuid):
    category = get_object_or_404(Category, uuid=uuid, owner=request.user)

    if request.method == "POST":
        name = request.POST["name"]
        try:
            CategoryService.update_category(category=category, name=name)
        except Exception as e:
            return render(
                request,
                "wallet/category/_form.html",
                {"category": category, "error": str(e)},
            )
        response = HttpResponse()
        response["HX-Redirect"] = reverse("category_list")
        return response

    return render(request, "wallet/category/_form.html", {"category": category})


@login_required
def category_delete(request, uuid):
    category = get_object_or_404(Category, uuid=uuid, owner=request.user)

    if request.method == "POST":
        CategoryService.delete_category(category)
        response = HttpResponse()
        response["HX-Redirect"] = reverse("category_list")
        return response

    return render(
        request, "wallet/category/_confirm_delete.html", {"category": category}
    )


@login_required
def import_csv(request):
    wallets = WalletService.list_wallets(request.user)

    if request.method == "POST" and request.FILES.get("file"):
        csv_file = request.FILES["file"]
        categories = CategoryService.list_categories(request.user)
        category_names = {c.name for c in categories}

        rows = []
        reader = csv.DictReader(csv_file.read().decode("utf-8-sig").splitlines(), delimiter=";")
        for i, row in enumerate(reader):
            rows.append(
                {
                    "index": i,
                    "amount": row.get("Total", "").strip(),
                    "description": row.get("Description", "").strip(),
                    "date": row.get("When", "").strip(),
                    "category_name": row.get("Category", "").strip(),
                }
            )

        csv_categories = sorted({r["category_name"] for r in rows if r["category_name"]})

        request.session["import_rows"] = rows
        request.session["import_category_names"] = list(category_names)

        return render(
            request,
            "wallet/import_csv.html",
            {
                "rows": rows,
                "wallets": wallets,
                "categories": categories,
                "csv_categories": csv_categories,
                "preview": True,
            },
        )

    if request.method == "POST" and request.POST.get("confirm"):
        rows = request.session.get("import_rows", [])
        category_names = set(request.session.get("import_category_names", []))
        wallet_uuid = request.POST.get("wallet")
        wallet = get_object_or_404(Wallet, uuid=wallet_uuid, owner=request.user)
        selected_indices = set(request.POST.getlist("selected_rows"))
        deduct = request.POST.get("deduct") == "on"

        category_map = {}
        for key, value in request.POST.items():
            if key.startswith("cat_map_"):
                csv_cat = key.removeprefix("cat_map_")
                if value:
                    category_map[csv_cat] = get_object_or_404(
                        Category, uuid=value, owner=request.user
                    )

        created = 0
        skipped = 0
        errors = []
        remaining = []

        for row in rows:
            if str(row["index"]) not in selected_indices:
                remaining.append(row)
                continue

            cat_name = row["category_name"]
            category = category_map.get(cat_name)
            if not category and cat_name:
                if cat_name not in category_names:
                    category = CategoryService.create_category(
                        owner=request.user, name=cat_name
                    )
                    category_names.add(cat_name)
                else:
                    category = Category.objects.get(
                        owner=request.user, name=cat_name
                    )

            try:
                amount = Decimal(row["amount"])
                tx_date = row["date"]

                duplicate = Transaction.objects.filter(
                    wallet=wallet,
                    amount=amount,
                    description=row["description"],
                    date=tx_date,
                    category=category,
                ).exists()

                if duplicate:
                    skipped += 1
                    continue

                if deduct:
                    WalletTransactionService.record_expense(
                        wallet=wallet,
                        balance=WalletBalanceService.get_balance(wallet),
                        amount=amount,
                        description=row["description"],
                        date=tx_date,
                        category=category,
                    )
                else:
                    WalletTransactionService.record_income(
                        wallet=wallet,
                        amount=amount,
                        description=row["description"],
                        date=tx_date,
                        category=category,
                    )
                created += 1
            except Exception as e:
                errors.append(f"Row {row['index'] + 2}: {e}")
                remaining.append(row)

        request.session["import_rows"] = remaining
        request.session["import_category_names"] = list(category_names)

        categories = CategoryService.list_categories(request.user)
        csv_categories = sorted({r["category_name"] for r in remaining if r["category_name"]})

        return render(
            request,
            "wallet/import_csv.html",
            {
                "rows": remaining,
                "wallets": wallets,
                "categories": categories,
                "csv_categories": csv_categories,
                "preview": True,
                "created": created,
                "skipped": skipped,
                "errors": errors,
            },
        )

    if request.method == "POST" and request.POST.get("finish"):
        request.session.pop("import_rows", None)
        request.session.pop("import_category_names", None)
        return HttpResponseRedirect(reverse("dashboard"))

    return render(
        request,
        "wallet/import_csv.html",
        {
            "wallets": wallets,
        },
    )
