from . import Module, register

register(Module(
    name="gpio_fan_led",
    peripherals=[
        'gpio_fan_led',
    ],
    default_config={
        'gpio_fan_led': 'follow',
        'gpio_fan_led_pin': 5,
    },
    depends_on=['gpio_fan'],
))
