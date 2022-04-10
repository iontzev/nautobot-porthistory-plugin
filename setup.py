from setuptools import find_packages, setup

setup(
    name='nautobot_porthistory_plugin',
    version='1.1.0',
    url='https://github.com/iontzev/nautobot-porthistory-plugin',
    description='Last outputs and MAC on ports history for ports of switches',
    author='Max Iontzev',
    author_email='iontzev@gmail.com',
    install_requires=[],
    packages=find_packages(),
    license='MIT',
    include_package_data=True,
    keywords=['nautobot', 'nautobot-plugin', 'plugin'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
)
