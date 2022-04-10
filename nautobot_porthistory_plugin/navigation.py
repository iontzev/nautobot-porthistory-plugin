"""Navigation Items to add to Nautobot for nautobot_porthistory_plugin."""

from nautobot.extras.plugins import PluginMenuItem

menu_items = (
    PluginMenuItem(
        link = 'plugins:nautobot_porthistory_plugin:history',  # A reverse compatible link to follow.
        link_text = 'MAC and IP on switches ports',  # Text to display to user.
    ),
)
