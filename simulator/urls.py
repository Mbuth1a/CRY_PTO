from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),

    path("api/market/", views.market_api, name="market_api"),
    
    path("api/events/", views.events_api, name="events_api"),
    path( "api/market/history/", views.market_history, name="market_history"),
    path("api/market/candles/", views.market_candles, name="market_candles",
    ),
     path(
        "register/",
        views.register,
        name="register",
    ),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="login.html"
        ),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path(
        "dashboard/",
        views.dashboard,
        name="dashboard",
    ),

    path(
        "api/wallet/purchase/",
        views.purchase_au,
        name="purchase-au",
    ),

    path(
        "api/withdraw/",
        views.withdrawal_api,
        name="withdraw-au",
    ),

    path(
        "api/portfolio/",
        views.portfolio_api,
        name="portfolio",
    ),
    path(
    "api/withdrawal/estimate/",
    views.withdrawal_estimate,
    name="withdrawal_estimate",
    ),
    path(
        "api/transactions/",
        views.transaction_history_api,
        name="transaction_history_api",
    ),
    path("", views.site_entry, name="site_entry"),
]