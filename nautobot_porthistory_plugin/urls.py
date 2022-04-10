"""Urls for nautobot_porthistory_plugin."""

from django.urls import path

from nautobot_porthistory_plugin import views

urlpatterns = [
    path('history/', views.PortHistoryView.as_view(), name='history'),
]