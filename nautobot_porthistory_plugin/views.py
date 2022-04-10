"""Views for nautobot_porthistory_plugin."""

from django.shortcuts import render
from nautobot.core.views import generic

from nautobot_porthistory_plugin import models, tables, filters, forms

class PortHistoryView(generic.ObjectListView):
    """Показывает MAC и IP адреса на портах"""

    queryset = models.MAConPorts.objects.all()
    table = tables.PortHistoryTable
    filterset = filters.PortHistoryFilterSet
    filterset_form = forms.PortHistoryFilterForm

    action_buttons = ()


