from . import Module, register

register(Module(
    name="oled",
    peripherals=[
        'oled',
        'oled_sleep',
        'oled_page_mix',
        'oled_page_performance',
        'oled_page_ips',
        'oled_page_disk',
    ],
    default_config={
        'oled_enable': True,
        'oled_rotation': 0,
        'oled_sleep_timeout': 10,
        'oled_pages': [
            'mix',
            'performance',
            'ips',
            'disk',
        ],
    },
))
