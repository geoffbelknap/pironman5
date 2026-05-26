from . import Module, register

register(Module(
    name="pwm_fan",
    peripherals=[
        'pwm_fan_speed',
    ],
))
