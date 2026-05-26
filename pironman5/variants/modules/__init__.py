class Module:
    """A hardware feature module with its own peripherals, config, and event map."""

    def __init__(
        self,
        name,
        peripherals=None,
        default_config=None,
        event_map=None,
        depends_on=None,
        dt_overlays=None,
    ):
        self.name = name
        self.peripherals = peripherals or []
        self.default_config = default_config or {}
        self.event_map = event_map or {}
        self.depends_on = depends_on or []
        self.dt_overlays = dt_overlays or []


_registry = {}


def register(module):
    if module.name in _registry:
        raise ValueError(f"Module '{module.name}' is already registered")
    _registry[module.name] = module


def get(name):
    if name not in _registry:
        raise KeyError(f"Module '{name}' not found. Available: {sorted(_registry.keys())}")
    return _registry[name]


def resolve_dependencies(module_names):
    """Topological resolve: dependencies appear before their dependents. Deduplicates."""
    resolved = []
    seen = set()

    def _resolve(name):
        if name in seen:
            return
        seen.add(name)
        mod = get(name)
        for dep in mod.depends_on:
            _resolve(dep)
        resolved.append(name)

    for name in module_names:
        _resolve(name)
    return resolved


def assemble(module_names):
    """Resolve deps, then merge peripherals, config, event_map, dt_overlays from modules."""
    resolved = resolve_dependencies(module_names)

    peripherals = []
    config = {}
    event_map = {}
    dt_overlays = []

    for name in resolved:
        mod = get(name)
        for p in mod.peripherals:
            if p not in peripherals:
                peripherals.append(p)
        config.update(mod.default_config)
        event_map.update(mod.event_map)
        for d in mod.dt_overlays:
            if d not in dt_overlays:
                dt_overlays.append(d)

    return {
        "peripherals": peripherals,
        "default_config": config,
        "event_map": event_map,
        "dt_overlays": dt_overlays,
    }


# Auto-discover and import all sibling module files
import importlib
import pkgutil

for _importer, _modname, _ispkg in pkgutil.iter_modules(__path__):
    if _modname != "__init__":
        importlib.import_module(f".{_modname}", __package__)
