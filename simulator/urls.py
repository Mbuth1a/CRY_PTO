from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),

    path("api/market/", views.market_api, name="market_api"),
    path("api/deposit/", views.deposit_api, name="deposit_api"),
    path("api/withdraw/", views.withdrawal_api, name="withdrawal_api"),
    path("api/convert/", views.convert_api, name="convert_api"),
    path("api/position/", views.position_api, name="position_api"),
    path("api/events/", views.events_api, name="events_api"),
    path( "api/market/history/", views.market_history, name="market_history"),
    path("api/market/candles/", views.market_candles, name="market_candles",
    ),
]