from nautobot.extras.choices import CustomFieldTypeChoices

def create_custom_fields_for_porthistory(sender, apps, **kwargs):
    """Create a custom field flag_porthistory for VLAN if it doesn't already exist."""
    # Use apps.get_model to look up Nautobot core models
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    VLAN = apps.get_model("ipam", "VLAN")
    Interface = apps.get_model("dcim", "Interface")

    # Create custom fields
    cf_for_vlan, created = CustomField.objects.update_or_create(
        name="flag-porthistory",
        defaults={
            "label": "Search MACs on ports in this VLAN",
            "type": CustomFieldTypeChoices.TYPE_BOOLEAN,
        },
    )
    cf_for_vlan.content_types.set([ContentType.objects.get_for_model(VLAN)])
    cf_for_interface, created = CustomField.objects.update_or_create(
        name="flag-ignore-mac",
        defaults={
            "label": "Ignore MACs on this port",
            "type": CustomFieldTypeChoices.TYPE_BOOLEAN,
        },
    )
    cf_for_interface.content_types.set([ContentType.objects.get_for_model(Interface)])
