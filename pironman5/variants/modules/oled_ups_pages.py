from . import Module, register

register(Module(
    name="oled_ups_pages",
    peripherals=[
        'oled_page_battery',
        'oled_page_input',
        'oled_page_rpi_power',
    ],
))
