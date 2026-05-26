class Pironman5ProMax:
    NAME = "Pironman 5 Pro Max"
    ID = "pironman5-pro-max"
    PRODUCT_VERSION = ""
    PERIPHERALS = [
        'storage',
        "cpu",
        "network",
        "memory",
        "history",
        "log",
        "ws2812",
        "cpu_temperature",
        "gpu_temperature",
        "temperature_unit",
        "oled",
        'oled_page_mix',
        'oled_page_performance',
        'oled_page_ips',
        'oled_page_disk',
        "clear_history",
        "delete_log_file",
        'debug_level',
        "oled_sleep",
        "pi5_power_button",

        "restart_service",
        "reboot",
        "shutdown",
    ]
    SYSTEM_DEFAULT_CONFIG = {
        'data_interval': 1,
        'debug_level': 'INFO',
        "temperature_unit": "C",
        'database_retention_days': 30,
        "default_dashboard_page": "small",
        'enable_history': True,

        "rgb_color": "#ff3dbe",
        "rgb_brightness": 50,
        "rgb_style": "breathing",
        "rgb_speed": 50,
        "rgb_enable": True,
        "rgb_led_count": 18,
        "rgb_led_count_min": 18,
                        # Front 4 LED      CPU FAN LED   HAT_REAR LED   REAR UPPER FAN       REAR_BOTTOM_FAN
        "rgb_position": [17, 16, 15, 14,   7, 6, 5, 4,   13, 12,         11, 10, 9, 8,        3, 2, 1, 0],

        "oled_enable": True,
        "oled_rotation": 0,
        'oled_sleep_timeout': 10,
        'oled_pages': [
            'mix',
            'performance',
            'ips',
            'disk',
        ],
    }
    EVENT_MAP = {
        'pi5_power_button_click': 'oled_wake_page_next',
        'pi5_power_button_double_click': 'oled_page_prev',
        'pi5_power_button_long_press': 'oled_show_shutdown_screen',
        'pi5_power_button_long_press_released': 'shutdown',
    }
    DT_OVERLAYS = [
        'sunfounder-pironman5promax.dtbo',
    ]
    CONFIG_TXT = {
        'dtparam=spi': 'on',
        'dtparam=i2c_arm': 'on',
    }
