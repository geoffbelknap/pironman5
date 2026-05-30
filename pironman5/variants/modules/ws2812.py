from . import Module, register

register(Module(
    name="ws2812",
    peripherals=[
        'ws2812',
    ],
    default_config={
        'rgb_enable': True,
        'rgb_color': '#0a1aff',
        'rgb_brightness': 100,
        'rgb_style': 'breathing',
        'rgb_speed': 50,
        'rgb_led_count': 4,
        'rgb_led_count_min': 4,
        'rgb_mode': 'ambient',
        'rgb_profile': 'breathing-blue',
        'rgb_night_brightness': None,
        'rgb_night_start': None,
        'rgb_night_end': None,
    },
))
