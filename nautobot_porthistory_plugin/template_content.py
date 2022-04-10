from nautobot.extras.plugins import PluginTemplateExtension
from django.conf import settings

from .models import UnusedPorts, MAConPorts



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

class MAConInterface(PluginTemplateExtension):
    """Template extension to display MACs on the right side of the page."""

    model = 'dcim.interface'

    def right_page(self):
        PLUGIN_CFG = settings.PLUGINS_CONFIG['nautobot_porthistory_plugin']
        SWITCHES_ROLE_SLUG = PLUGIN_CFG['switches_role_slug']
        interface = self.context['object']

        if interface.device.device_role.slug in SWITCHES_ROLE_SLUG:
            nb_mac_on_ports = MAConPorts.objects.filter(interface=interface)
            mac_on_ports = []
            for mac in nb_mac_on_ports:
                mac_on_ports.append({
                    'mac': mac.mac,
                    'vlan': mac.vlan,
                    'ipaddress': mac.ipaddress,
                    'updated': mac.updated.strftime("%d.%m.%Y %H:%M"),
                })
            return self.render('mac_on_port.html', extra_context={
                'mac_on_ports': mac_on_ports,
            })
        else:
            return ''

class InterfaceWithIP(PluginTemplateExtension):
    """Template extension to display Interfaces on the right side of the page."""

    model = 'ipam.ipaddress'

    def right_page(self):
        PLUGIN_CFG = settings.PLUGINS_CONFIG['nautobot_porthistory_plugin']
        SWITCHES_ROLE_SLUG = PLUGIN_CFG['switches_role_slug']
        ipaddress = self.context['object']

        nb_ports_with_ipaddress = MAConPorts.objects.filter(ipaddress=ipaddress)
        ports_with_ipaddress = []
        for mac in nb_ports_with_ipaddress:
            ports_with_ipaddress.append({
                'mac': mac.mac,
                'vlan': mac.vlan,
                'interface': mac.interface,
                'updated': mac.updated.strftime("%d.%m.%Y %H:%M"),
            })
        return self.render('ports_with_ipaddress.html', extra_context={
            'ports_with_ipaddress': ports_with_ipaddress,
        })

template_extensions = [DeviceUnusedPorts, MAConInterface, InterfaceWithIP]