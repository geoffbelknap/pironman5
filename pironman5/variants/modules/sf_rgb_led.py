from . import Module, register

register(Module(
    name="sf_rgb_led",
    peripherals=[
        'sf_rgb_led',
    ],
    default_config={
        'rgb_enable': True,
        'rgb_color': '#0a1aff',
        'rgb_brightness': 100,
        'rgb_style': 'breathing',
        'rgb_speed': 50,
        'rgb_led_count': 23,
        'rgb_led_count_min': 1,
    },
))
