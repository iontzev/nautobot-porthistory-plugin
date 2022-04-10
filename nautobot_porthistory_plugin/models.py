"""Model definition for nautobot_porthistory_plugin."""

from django.db import models

from nautobot.core.models import BaseModel
from nautobot.dcim.fields import MACAddressCharField

class UnusedPorts(BaseModel):
    # Дата/время последнего output на порту коммутатора 

    updated = models.DateTimeField(auto_now=True)
    last_output = models.DateTimeField()
    interface = models.ForeignKey(
        to="dcim.Interface",
        on_delete=models.CASCADE,
        blank=False,
    )
    
    def __str__(self):
        return f'{self.interface.name} - {self.last_output}'

class MAConPorts(BaseModel):
    # MAC и IP на порту коммутатора 

    updated = models.DateTimeField(auto_now=True)
    mac = MACAddressCharField(blank=False, verbose_name="MAC Address")
    vlan = models.ForeignKey(
        to="ipam.VLAN",
        on_delete=models.CASCADE,
        blank=False,
    )
    ipaddress = models.ForeignKey(
        to="ipam.IPAddress",
        on_delete=models.SET_NULL,
        default=None,
        blank=True,
        null=True,
    )
    interface = models.ForeignKey(
        to="dcim.Interface",
        on_delete=models.CASCADE,
        blank=False,
    )
    device = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.CASCADE,
        blank=False,
    )
    
    def __str__(self):
        return f'{self.intervace} - VLAN {seld.vlan.vid} MAC {self.mac}'

    class Meta:
        verbose_name_plural = 'MAC and IP on switches ports'
