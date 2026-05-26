from . import Module, register

register(Module(
    name="gpio_fan",
    peripherals=[
        'gpio_fan_state',
        'gpio_fan_mode',
    ],
    default_config={
        'gpio_fan_pin': 6,
        'gpio_fan_mode': 0,
    },
))
