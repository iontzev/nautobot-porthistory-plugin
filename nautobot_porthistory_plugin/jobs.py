from django.contrib.contenttypes.models import ContentType

from nautobot.dcim.models import Device, DeviceRole, Site, Interface
from nautobot.extras.jobs import Job, ObjectVar
from nautobot.extras.models import Status
from django.conf import settings

from nautobot_porthistory_plugin.models import UnusedPorts

import asyncio
import aiosnmp

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

jobs = [UnusedPortsUpdate]