from . import Module, register

register(Module(
    name="vibration_switch",
    peripherals=[
        'vibration_switch',
    ],
))
