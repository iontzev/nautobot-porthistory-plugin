import django_tables2 as tables
from django_tables2.utils import A
from nautobot.utilities.tables import BaseTable, ToggleColumn

from nautobot_porthistory_plugin import models

class PortHistoryTable(BaseTable):
    pk = ToggleColumn()
    device = tables.Column(linkify=True)
    interface = tables.LinkColumn(orderable=False)
    vlan = tables.LinkColumn()
    ipaddress = tables.Column(linkify=True, verbose_name="IPv4 Address")

    class Meta(BaseTable.Meta):  # pylint: disable=too-few-public-methods
        """Meta attributes."""

        model = models.MAConPorts
        fields = (
            'pk',
            'device',
            'interface',
            'vlan',
            'mac',
            'ipaddress',
            'updated',
        )
