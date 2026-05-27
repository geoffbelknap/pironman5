from . import Module, register

register(Module(
    name="network_info",
    peripherals=[
        'ip_address',
        'mac_address',
    ],
))
