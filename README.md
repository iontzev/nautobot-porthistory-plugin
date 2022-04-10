# Nautobot Port History Plugin
Port history plugin for [Nautobot](https://github.com/nautobot/nautobot). Nautobot v1.0.0+ is required.

### Package Installation from Source Code
The source code is available on GitLab.<br/>
Download and install the package. Assuming you use a Virtual Environment for Nautobot:
```
$ sudo -iu nautobot
$ cd [directory with nautobot-porthistory-plugin]
$ pip3 install .
```
### Install requirements
The source code is available on GitLab.<br/>
Download and install the package. Assuming you use a Virtual Environment for Nautobot:
```
$ sudo -iu nautobot
$ pip3 install aiosnmp netutils
```

### Enable the Plugin
In a global Nautobot **nautobot_config.py** configuration file, update or add PLUGINS parameter:
```python
PLUGINS = [
    'nautobot_porthistory_plugin',
]
```

Update a PLUGINS_CONFIG parameter in **nautobot_config.py** to rewrite default plugin behavior:
```python
PLUGINS_CONFIG = {
    'nautobot_porthistory_plugin': {
        'switches_role_slug': ['Access-switch'],
        'routers_role_slug': ['Router'],
        'min_idle_days': 14,
        'snmp_community': 'public',
        'workers': 50,
     }
}
```
Parameters `switches_role_slug` and `routers_role_slug` is required. 

### Restart Nautobot
Restart the WSGI service to apply changes:
```
sudo systemctl restart nautobot
```

