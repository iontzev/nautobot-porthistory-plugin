from django.contrib.contenttypes.models import ContentType

from nautobot.dcim.models import Device, DeviceRole, Site, Interface, Cable
from nautobot.ipam.models import VLAN, IPAddress, Prefix
from nautobot.extras.jobs import Job, ObjectVar
from nautobot.extras.models import Status
from django.conf import settings

from nautobot_porthistory_plugin.models import UnusedPorts, MAConPorts

import asyncio
import aiosnmp
from ipaddress import IPv4Network, IPv4Address
import socket

from collections import defaultdict
from netutils.interface import canonical_interface_name
from datetime import datetime, timedelta

class UnusedPortsUpdate(Job):

    class Meta:
        name = "Обновление информации о неподключенных интерфейсах"

    site = ObjectVar(
        model=Site,
        label='БЮ',
        required=False
    )

    async def bulk_snmp(self, device, oid_list, community):
        oid_results = {}
        try:
            async with aiosnmp.Snmp(
                host=device,
                port=161,
                community=community,
                timeout=5,
                retries=3,
                max_repetitions=10,
            ) as snmp:
                oid_bulk_result = {}
                for oid in oid_list:
                    reply = await snmp.bulk_walk(oid)
                    for index in reply:
                        oid_bulk_result[index.oid] = index.value
                    oid_results[oid] = oid_bulk_result

                return (device, oid_results)

        except Exception as error:
            return (device, error)
        return (device, None)

    async def bulk_snmp_with_semaphore(self, semaphore, function, *args, **kwargs):
        async with semaphore:
            return await function(*args, **kwargs)

    async def async_bulk_snmp(self, devices, oid_list, community, workers):
        semaphore = asyncio.Semaphore(workers)
        coroutines = [
            self.bulk_snmp_with_semaphore(semaphore, self.bulk_snmp, device, oid_list, community)
            for device in devices
        ]
        result = []
        for future in asyncio.as_completed(coroutines):
            result.append(await future)
        return result

    def round_datetime(self, date):
        date_tuple = date.timetuple()
        return datetime(year=date_tuple.tm_year,
                        month=date_tuple.tm_mon,
                        day=date_tuple.tm_mon,
                        hour=date_tuple.tm_hour, minute=0, second=0, microsecond=0
                        )

    def run(self, data, commit):
        # запускать job могут только пользователи is_superuser
        if not self.request.user.is_superuser:
            self.log_info(message='Неавторизованный запуск')
            return

        PLUGIN_CFG = settings.PLUGINS_CONFIG['nautobot_porthistory_plugin']
        COMMUNITY = PLUGIN_CFG['snmp_community']
        MIN_IDLE_DAYS = PLUGIN_CFG.get('min_idle_days', 14)
        SWITCHES_ROLE_SLUG = PLUGIN_CFG['switches_role_slug']
        WORKERS = PLUGIN_CFG['workers']
        STATUS_ACTIVE = Status.objects.get(slug='active')

        # сгенерируем справочник устройств
        devices = [] #этот список передадим в модуль snmp
        device_dict = defaultdict(dict)
        device_role = DeviceRole.objects.filter(slug__in=SWITCHES_ROLE_SLUG)
        if data['site']:
            nb_devices = Device.objects.filter(site=data['site'], device_role__in=device_role, status=STATUS_ACTIVE)
        else:
            nb_devices = Device.objects.filter(device_role__in=device_role, status=STATUS_ACTIVE)
            
        for nb_device in nb_devices:
            if nb_device.platform and nb_device.platform.napalm_driver and nb_device.platform.napalm_driver == 'cisco_iosxe' and nb_device.primary_ip4:
                primary_ip = str(nb_device.primary_ip4).split('/')[0]
                devices.append(primary_ip)
                device_dict[primary_ip]['device'] = nb_device
                device_dict[primary_ip]['interfaces'] = {}
                device_dict[primary_ip]['ifindexes'] = {}
                device_interfaces = Interface.objects.filter(device_id=nb_device)
                for intf in device_interfaces:
                    device_dict[primary_ip]['interfaces'][intf.name] = [intf]

        # получим uptime оборудования по SNMP (в секундах)
        # и занесем эту информацию в справочник
        oid_list = ['.1.3.6.1.6.3.10.2.1.3']
        results = asyncio.run(self.async_bulk_snmp(devices, oid_list, COMMUNITY, WORKERS))
        for device_ip, device_result in results:
            if type(device_result) != dict:
                self.log_warning(obj=device_dict[device_ip]['device'],message=f'не удалось получить информацию по SNMP - {device_result}')
                continue
            for oid, oid_result in device_result.items():
                for uptime in oid_result.values():
                    device_dict[device_ip]['uptime'] = uptime
                    boottime = datetime.now() - timedelta(seconds=uptime)
                    device_dict[device_ip]['boottime'] = boottime
    
        # получим названия интерфейсов и их индексы с оборудования по SNMP
        # и занесем эту информацию в справочник
        oid_list = ['.1.3.6.1.2.1.31.1.1.1.1']
        results = asyncio.run(self.async_bulk_snmp(devices, oid_list, COMMUNITY, WORKERS))
        for device_ip, device_result in results:
            if type(device_result) != dict or 'uptime' not in device_dict[device_ip]:
                continue
            for oid, oid_result in device_result.items():
                for index, index_result in oid_result.items():
                    ifindex = index.split('.')[-1]
                    canonical_intf_name = canonical_interface_name(index_result.decode("utf-8"))
                    if canonical_intf_name in device_dict[device_ip]['interfaces']:
                        device_dict[device_ip]['ifindexes'][ifindex] = canonical_intf_name

        # получим время последнего output по SNMP
        oid_list = ['.1.3.6.1.4.1.9.2.2.1.1.4']
        results = asyncio.run(self.async_bulk_snmp(devices, oid_list, COMMUNITY, WORKERS))
        output = ''
        for device_ip, device_result in results:
            if type(device_result) != dict or 'uptime' not in device_dict[device_ip]:
                continue
            nb_device = device_dict[device_ip]['device']
            boottime = device_dict[device_ip]['boottime']
            uptime = device_dict[device_ip]['uptime']
            output += f'{nb_device.name} - power on {boottime}\n'
            unused_port_count = 0
            for oid, oid_result in device_result.items():
                for index, time_from_last_output in oid_result.items():
                    ifindex = index.split('.')[-1]
                    if ifindex in device_dict[device_ip]['ifindexes']:
                        intf_name = device_dict[device_ip]['ifindexes'][ifindex]
                        nb_interface = device_dict[device_ip]['interfaces'][intf_name][0]
                        if time_from_last_output < 0 or time_from_last_output / 1000 > uptime - 300:
                            unused_port_count += 1
                            unused_port, created = UnusedPorts.objects.get_or_create(
                                interface=nb_interface,
                                defaults={
                                    'last_output': boottime
                                }
                            )
                            unused_port.save()
                        else:
                            last_output = datetime.now() - timedelta(seconds=round(time_from_last_output/1000))
                            if 1000 * 60 * 60 * 24 * MIN_IDLE_DAYS > time_from_last_output:
                                # прошло меньше MIN_IDLE_DAYS дней
                                UnusedPorts.objects.filter(interface=nb_interface).delete()
                            else:
                                unused_port_count += 1
                                unused_port, created = UnusedPorts.objects.get_or_create(
                                    interface=nb_interface,
                                    defaults={
                                        'last_output': last_output
                                    }
                                )
                                if not created:
                                    unused_port.last_output = last_output
                                    unused_port.save()
            output += f'неиспользуемых в течении {MIN_IDLE_DAYS} дн. портов - {unused_port_count}\n'

        return output

class MAConPortsUpdate(Job):

    class Meta:
        name = "Обновление информации о подключенных устройствах"

    site = ObjectVar(
        model=Site,
        label='БЮ',
        required=False
    )

    async def bulk_snmp(self, device, oid_list, community):
        oid_results = {}
        try:
            async with aiosnmp.Snmp(
                host=device,
                port=161,
                community=community,
                timeout=5,
                retries=3,
                max_repetitions=10,
            ) as snmp:
                oid_bulk_result = {}
                for oid in oid_list:
                    reply = await snmp.bulk_walk(oid)
                    for index in reply:
                        oid_bulk_result[index.oid] = index.value
                    oid_results[oid] = oid_bulk_result

                return (device, oid_results)

        except Exception as error:
            return (device, error)
        return (device, None)

    async def bulk_snmp_with_semaphore(self, semaphore, function, *args, **kwargs):
        async with semaphore:
            return await function(*args, **kwargs)

    async def async_bulk_snmp(self, devices, oid_list, community, workers):
        semaphore = asyncio.Semaphore(workers)
        coroutines = [
            self.bulk_snmp_with_semaphore(semaphore, self.bulk_snmp, device, oid_list, community)
            for device in devices
        ]
        result = []
        for future in asyncio.as_completed(coroutines):
            result.append(await future)
        return result

    def run(self, data, commit):
        # запускать job могут только пользователи is_superuser
        if not self.request.user.is_superuser:
            self.log_info(message='Неавторизованный запуск')
            return

        PLUGIN_CFG = settings.PLUGINS_CONFIG['nautobot_porthistory_plugin']
        COMMUNITY = PLUGIN_CFG['snmp_community']
        SWITCHES_ROLE_SLUG = PLUGIN_CFG['switches_role_slug']
        ROUTERS_ROLE_SLUG = PLUGIN_CFG['routers_role_slug']
        WORKERS = PLUGIN_CFG['workers']
        STATUS_ACTIVE = Status.objects.get(slug='active')
        STATUS_STATIC = Status.objects.get(slug='static')
        STATUS_DHCP = Status.objects.get(slug='dhcp')

        device_role = DeviceRole.objects.filter(slug__in=SWITCHES_ROLE_SLUG)

        devices = defaultdict(dict)
        devices_list = []
        vlans = defaultdict(list)

        # построим список всех связей, чтобы потом исключить из результатов линки между свичами
        cable_set = defaultdict(set)
        all_cables = Cable.objects.all()
        for cable in all_cables:
            if cable.termination_a_type == ContentType.objects.get(app_label='dcim', model='interface'):
                if not data['site'] or cable.termination_a.device.site == data['site']:
                    cable_set[cable.termination_a.device.name].add(cable.termination_a.name)
            if cable.termination_b_type == ContentType.objects.get(app_label='dcim', model='interface'):
                if not data['site'] or cable.termination_b.device.site == data['site']:
                    cable_set[cable.termination_b.device.name].add(cable.termination_b.name)

        # сгенерируем справочник вланов с разбивкой по сайтам
        vlans_by_site = defaultdict(list)
        if data['site']:
            nb_vlans = VLAN.objects.filter(site=data['site'], status=STATUS_ACTIVE, _custom_field_data={'flag-porthistory':True})
        else:
            nb_vlans = VLAN.objects.filter(status=STATUS_ACTIVE, _custom_field_data={'flag-porthistory':True})
        for nb_vlan in nb_vlans:
            vlans_by_site[nb_vlan.site.name].append(nb_vlan.vid)

        # сгенерируем справочник устройств
        for site in vlans_by_site:
            site_id = Site.objects.get(name=site)
            nb_devices_in_site = Device.objects.filter(
                site=site_id, 
                device_role__in=device_role, 
                status=STATUS_ACTIVE,
            )
            for nb_device in nb_devices_in_site:
                if (nb_device.platform and 
                            nb_device.platform.napalm_driver and 
                            nb_device.platform.napalm_driver == 'cisco_iosxe' and 
                            nb_device.primary_ip4):

                    primary_ip = str(nb_device.primary_ip4).split('/')[0]
                    devices_list.append(primary_ip)
                    device = devices[primary_ip] = {}
                    device['device'] = nb_device
                    device['site'] = nb_device.site
                    device['interfaces'] = {}
                    device['ifindexes'] = {}
                    device['bridge_ports'] = {}
                    device['vlans'] = vlans_by_site[site]
                    for intf in Interface.objects.filter(device_id=nb_device):
                        device['interfaces'][intf.name] = intf
                    for vlan in vlans_by_site[site]:
                        vlans[vlan].append(primary_ip)

        # получим названия интерфейсов и их индексы с оборудования по SNMP
        oid_list = ['.1.3.6.1.2.1.31.1.1.1.1']
        results = asyncio.run(self.async_bulk_snmp(devices_list, oid_list, COMMUNITY, WORKERS))
        for device_ip, device_result in results:
            if type(device_result) != dict:
                self.log_warning(obj=devices[device_ip]['device'],message=f'не удалось получить информацию по SNMP')
                del devices[device_ip]
                devices_list.remove(device_ip)
                continue
            for oid, oid_result in device_result.items():
                for index, index_result in oid_result.items():
                    ifindex = index.split('.')[-1]
                    canonical_intf_name = canonical_interface_name(index_result.decode("utf-8"))
                    if canonical_intf_name in devices[device_ip]['interfaces']:
                        devices[device_ip]['ifindexes'][ifindex] = canonical_intf_name

        # пройдемся по списку вланов и получим с устройства таблицу MAC адресов для каждого влана
        # MAC адреса в десятичном формате

        port_mac_relation = defaultdict(list)

        for vlan, devices_dict in vlans.items():
            self.log_info(message=f'Получаем информацию по VLAN {vlan}')
            community_with_vlan = f'{COMMUNITY}@{vlan}'
            devices_list = [device for device in devices_dict if device in devices_list]

            # получим bridge ports с оборудования по SNMP (зависит от VLAN)
            oid_list = ['.1.3.6.1.2.1.17.1.4.1.2']
            results = asyncio.run(self.async_bulk_snmp(devices_list, oid_list, community_with_vlan, WORKERS))
            for device_ip, device_result in results:
                if type(device_result) != dict:
                    # скорее всего, такого VLAN нет на этом устройстве
                    continue
                for oid, oid_result in device_result.items():
                    for index, index_result in oid_result.items():
                        bridge_port = index.split('.')[-1]
                        ifindex = str(index_result)
                        if ifindex in devices[device_ip]['ifindexes']:
                            ifname = devices[device_ip]['ifindexes'][ifindex]
                            nb_interface = devices[device_ip]['interfaces'][ifname]
                            devices[device_ip]['bridge_ports'][bridge_port] = nb_interface
            else:
                oid_list = ['.1.3.6.1.2.1.17.4.3.1.2']

                results = asyncio.run(self.async_bulk_snmp(devices_list, oid_list, community_with_vlan, WORKERS))
                for device_ip, device_result in results:
                    nb_device = devices[device_ip]['device']
                    nb_vlan = VLAN.objects.get(vid=vlan, site_id=nb_device.site.id)
                    if type(device_result) != dict:
                        continue
                    for oid, oid_result in device_result.items():
                        for mac_dec, bridge_port in oid_result.items():
                            if str(bridge_port) in devices[device_ip]['bridge_ports']:
                                if (devices[device_ip]['bridge_ports'][str(bridge_port)].name not in cable_set[nb_device.name]
                                        and not devices[device_ip]['bridge_ports'][str(bridge_port)]._custom_field_data.get('flag-ignore-mac')):
                                    # преобразуем MAC из десятичного формата в шестнадцатеричный
                                    mac_hex = ''.join(['{0:x}'.format(int(i)).zfill(2) for i in mac_dec.split('.')[-6:]]).upper()
                                    port_mac_relation[devices[device_ip]['bridge_ports'][str(bridge_port)].id].append({
                                        'vlan': nb_vlan,
                                        'mac': mac_hex,
                                        })

        # подготовим список L3 устройств
        routers = defaultdict(dict)
        routers_list = []
        device_role = DeviceRole.objects.filter(slug__in=ROUTERS_ROLE_SLUG)
        for site in vlans_by_site:
            site_id = Site.objects.get(name=site)
            nb_devices_in_site = Device.objects.filter(
                site=site_id, 
                device_role__in=device_role, 
                status=STATUS_ACTIVE,
            )
            for nb_device in nb_devices_in_site:
                if (nb_device.platform and 
                            nb_device.platform.napalm_driver and 
                            nb_device.platform.napalm_driver == 'cisco_iosxe' and 
                            nb_device.primary_ip4):

                    primary_ip = str(nb_device.primary_ip4).split('/')[0]
                    routers_list.append(primary_ip)
                    router = routers[primary_ip] = {}
                    router['site'] = nb_device.site.name
                    router['device'] = nb_device

        arp = defaultdict(dict)
        # получим ARP-таблицу с оборудования по SNMP
        oid_list = ['.1.3.6.1.2.1.3.1.1.2']
        results = asyncio.run(self.async_bulk_snmp(routers_list, oid_list, COMMUNITY, WORKERS))
        for device_ip, device_result in results:
            site = routers[device_ip]['site']
            arp[site] = defaultdict(list)
            if type(device_result) != dict:
                self.log_warning(obj=routers[device_ip]['device'],message=f'не удалось получить информацию по SNMP')
                continue
            for oid, oid_result in device_result.items():
                for index, index_result in oid_result.items():
                    snmp_address = '.'.join(index.split('.')[-4:])
                    snmp_mac = ''.join(["{0:x}".format(int(i)).zfill(2) for i in index_result]).upper()
                    arp[site][snmp_mac].append(snmp_address)

        output = ''

        for device in devices.values():
            nb_device = device['device']
            site = nb_device.site.name
            output += f'device {nb_device} :'
            mac_on_device = ip_on_device = name_on_device = 0
            for intf in device['interfaces'].values():
                if len(port_mac_relation[intf.id]) > 0:
                    MAConPorts.objects.filter(interface=intf).delete()
                for vlan_and_mac in port_mac_relation[intf.id]:
                    mac_on_device += 1
                    nb_prefixes = Prefix.objects.filter(vlan_id=vlan_and_mac['vlan'].id)
                    addresses = arp[site].get(vlan_and_mac['mac'])
                    address_with_prefix = ''
                    if nb_prefixes and addresses:
                        for nb_prefix in nb_prefixes:
                            for address in addresses:
                                if IPv4Address(address) in IPv4Network(str(nb_prefix)):
                                    prefixlen = str(nb_prefix).split('/')[-1]
                                    address_with_prefix = f'{address}/{prefixlen}'
                                    break
                            else:
                                continue
                            break
                    if address_with_prefix:
                        ip_on_device += 1
                        try:
                            hostname, aliaslist, ipaddrlist  = socket.gethostbyaddr(address)
                            name_on_device += 1
                        except:
                            hostname=''
                        nb_address, created = IPAddress.objects.get_or_create(
                            address=address_with_prefix,
                            vrf=nb_prefix.vrf,
                            defaults={
                                'status': STATUS_STATIC,
                                'dns_name': hostname
                            }
                        )
                        if created:
                            self.log_success(obj=nb_address, message=f'Добавлен IP адрес {hostname}')
                        elif nb_address.status != STATUS_DHCP and hostname and nb_address.dns_name != hostname:
                            old_hostname = nb_address.dns_name
                            nb_address.dns_name = hostname
                            nb_address.save()
                            self.log_success(obj=nb_address, message=f'Обновлено DNS name "{old_hostname}" -> "{hostname}"')
                    else:
                        nb_address = None
                    mac, created = MAConPorts.objects.get_or_create(
                        vlan=vlan_and_mac['vlan'],
                        mac=vlan_and_mac['mac'],
                        defaults={
                            'interface': intf,
                            'device': nb_device,
                            'ipaddress': nb_address,
                        }
                    )
                    if not created:
                        updated = False
                        if nb_address and mac.ipaddress != nb_address:
                            self.log_info(obj=nb_address, message=f'Устройство с MAC {mac.mac} поменяло IP {mac.ipaddress} -> {nb_address}')
                            mac.ipaddress = nb_address
                            updated = True
                        if mac.interface != intf:
                            self.log_info(obj=intf, message=f'MAC {mac.mac} переехал с порта "{mac.interface}"')
                            mac.interface = intf
                            mac.device = nb_device
                            updated = True
                        if updated:
                            mac.save()

            output += f" MAC count - {mac_on_device}, IP count - {ip_on_device}, resolved to hostname - {name_on_device}\n"

        return output

jobs = [UnusedPortsUpdate, MAConPortsUpdate]