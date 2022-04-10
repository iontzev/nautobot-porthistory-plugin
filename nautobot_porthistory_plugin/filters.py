import django_filters
from nautobot.dcim.models import Device
from nautobot.utilities.filters import BaseFilterSet, MultiValueCharFilter
from django.db.models import Q

from nautobot_porthistory_plugin.models import MAConPorts

class PortHistoryFilterSet(BaseFilterSet):
    """Filter for MAConPorts"""

    q = django_filters.CharFilter(method="search", label="Search MAC")

    site = MultiValueCharFilter(
        method="filter_site",
        field_name="pk",
        label="site",
    )
    device_id = MultiValueCharFilter(
        method="filter_device_id",
        field_name="pk",
        label="Device (ID)",
    )
    vlan = MultiValueCharFilter(
        method="filter_vlan",
        field_name="pk",
        label="VLAN",
    )

    class Meta:
        """Meta attributes for filter."""

        model = MAConPorts

        fields = [
            'vlan'
        ]

    def search(self, queryset, mac, value):
        if not value.strip():
            return queryset
        mac = ''.join(ch for ch in value if ch.isalnum())
        mac = ':'.join(mac[i:i+2] for i in range(0,len(mac),2))
        return queryset.filter(Q(mac__icontains=mac))

    def filter_site(self, queryset, name, id_list):
        if not id_list:
            return queryset
        return queryset.filter(Q(device__site__slug__in=id_list) )

    def filter_device_id(self, queryset, name, id_list):
        if not id_list:
            return queryset
        return queryset.filter(Q(device__id__in=id_list) )

    def filter_vlan(self, queryset, name, id_list):
        if not id_list:
            return queryset
        return queryset.filter(Q(vlan__id__in=id_list) )
