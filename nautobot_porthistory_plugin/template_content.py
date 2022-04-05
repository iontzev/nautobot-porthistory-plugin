from nautobot.extras.plugins import PluginTemplateExtension
from django.conf import settings

from .models import UnusedPorts



class DeviceUnusedPorts(PluginTemplateExtension):
    """Template extension to display unused ports on the right side of the page."""

    model = 'dcim.device'

    def right_page(self):
        PLUGIN_CFG = settings.PLUGINS_CONFIG['nautobot_porthistory_plugin']
        SWITCHES_ROLE_SLUG = PLUGIN_CFG['switches_role_slug']
        MIN_IDLE_DAYS = PLUGIN_CFG.get('min_idle_days', 14)
        device = self.context['object']

        if device.device_role.slug in SWITCHES_ROLE_SLUG:
            device_intefaces = device.interfaces.values_list("id", flat=True)
            unused_ports = UnusedPorts.objects.filter(interface_id__in=device_intefaces)
            unused_ports_with_delta = []
            for port in unused_ports:
                unused_ports_with_delta.append({
                    'interface_name': port.interface.name,
                    'last_output': port.last_output.strftime("%d.%m.%Y %H:%M"),
                    'updated': port.updated.strftime("%d.%m.%Y %H:%M"),
                    'delta': str(port.updated - port.last_output).split()[0]
                })
            return self.render('unused_ports.html', extra_context={
                'unused_ports': unused_ports_with_delta,
                'min_idle_days': MIN_IDLE_DAYS
            })
        else:
            return ''

template_extensions = [DeviceUnusedPorts]