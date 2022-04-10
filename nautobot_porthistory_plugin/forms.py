from django import forms

from nautobot.dcim.models import Region, Site, Device
from nautobot.ipam.models import VLAN
from nautobot.utilities.forms import BootstrapMixin, DynamicModelMultipleChoiceField
from nautobot.extras.forms import CustomFieldFilterForm

from nautobot_porthistory_plugin.models import MAConPorts

class PortHistoryFilterForm(BootstrapMixin, forms.Form):
    """Filter form to filter searches for MAC."""

    model = MAConPorts
    field_order = ["q", "site", "device_id", "vlan"]
    q = forms.CharField(required=False, label="Search MAC")
    site = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        to_field_name="slug",
        required=False,
    )
    device_id = DynamicModelMultipleChoiceField(
        queryset=Device.objects.all(),
        required=False,
        label="Device",
        query_params={"site": "$site"},
    )
    vlan = DynamicModelMultipleChoiceField(
        queryset=VLAN.objects.all(),
        required=False,
        label="VLAN",
        query_params={"site": "$site"},
    )

