"""Model definition for nautobot_porthistory_plugin."""

from django.db import models

from nautobot.core.models import BaseModel

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
