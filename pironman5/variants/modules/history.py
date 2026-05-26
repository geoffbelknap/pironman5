from . import Module, register

register(Module(
    name="history",
    peripherals=[
        'history',
        'clear_history',
    ],
    default_config={
        'enable_history': True,
    },
))
