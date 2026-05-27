from . import Module, register

register(Module(
    name="pi5_power_button",
    peripherals=[
        'pi5_power_button',
    ],
    event_map={
        'pi5_power_button_click': 'oled_wake_page_next',
        'pi5_power_button_double_click': 'oled_page_prev',
        'pi5_power_button_long_press': 'oled_show_shutdown_screen',
        'pi5_power_button_long_press_released': 'shutdown',
    },
))
