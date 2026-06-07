from django.urls import path

from wallet import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("signup/", views.signup_view, name="signup"),
    path("wallets/create/", views.wallet_create, name="wallet_create"),
    path("wallets/<uuid:uuid>/", views.wallet_detail, name="wallet_detail"),
    path("wallets/<uuid:uuid>/update/", views.wallet_update, name="wallet_update"),
    path("wallets/<uuid:uuid>/delete/", views.wallet_delete, name="wallet_delete"),
    path("wallets/<uuid:uuid>/transfer/", views.wallet_transfer_fast, name="wallet_transfer_fast"),
    path(
        "wallets/<uuid:wallet_uuid>/transactions/create/",
        views.transaction_create,
        name="transaction_create",
    ),
    path(
        "wallets/<uuid:wallet_uuid>/transactions/<uuid:uuid>/update/",
        views.transaction_update,
        name="transaction_update",
    ),
    path(
        "wallets/<uuid:wallet_uuid>/transactions/<uuid:uuid>/delete/",
        views.transaction_delete,
        name="transaction_delete",
    ),
    path("categories/", views.category_list, name="category_list"),
    path("categories/create/", views.category_create, name="category_create"),
    path("categories/<uuid:uuid>/update/", views.category_update, name="category_update"),
    path("categories/<uuid:uuid>/delete/", views.category_delete, name="category_delete"),
]
