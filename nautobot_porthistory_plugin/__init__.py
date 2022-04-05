"""nautobot_porthistory_plugin Plugin Initilization."""

from nautobot.extras.plugins import PluginConfig


class NautobotPorthistoryPluginConfig(PluginConfig):
    """Plugin configuration for the nautobot_porthistory_plugin plugin."""

    name = "nautobot_porthistory_plugin"
    verbose_name = "PortHistory plugin"
    description = 'Nautobot plugin for show port history (last output)'
    base_url = "nautobot_porthistory_plugin"
    version = '1.0.0'
    author = 'Max Iontzev'
    author_email = 'iontzev@gmail.com'
    min_version = "1.0.0"  # Minimum version of Nautobot with which the plugin is compatible.
    max_version = "1.999"  # Maximum version of Nautobot with which the plugin is compatible.
    default_settings = {
        'min_idle_days': 14,
        'snmp_community': 'public',
        'workers': 50,
    }
    required_settings = ['switches_role_slug']
    caching_config = {}

config = NautobotPorthistoryPluginConfig