from . import Module, register

register(Module(
    name="core",
    peripherals=[
        'storage',
        'cpu',
        'network',
        'memory',
        'log',
        'cpu_temperature',
        'gpu_temperature',
        'temperature_unit',
        'delete_log_file',
        'debug_level',
        'restart_service',
        'reboot',
        'shutdown',
    ],
    default_config={
        'data_interval': 1,
        'database_retention_days': 30,
        'temperature_unit': 'C',
    },
))
