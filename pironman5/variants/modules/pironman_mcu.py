from . import Module, register

register(Module(
    name="pironman_mcu",
    peripherals=[
        'pironman_mcu',
    ],
    event_map={
        'pironman_mcu_button_click': 'oled_wake_page_next',
        'pironman_mcu_button_double_click': 'oled_page_prev',
        'pironman_mcu_button_long_press': 'oled_show_shutdown_screen',
        'pironman_mcu_button_long_press_released': 'shutdown',
    },
))
