import json
import time
import os
from importlib import metadata
import signal

from .logger import Logger
from .utils import merge_dict, log_error
from .security import redact_secrets, write_json_private
from .history import SQLiteHistory
from .version import __version__ as pironman5_version
from .variants import NAME, ID, PRODUCT_VERSION, PERIPHERALS, SYSTEM_DEFAULT_CONFIG, EVENT_MAP
from ._constants import CONFIG_PATH, APP_NAME, DEFAULT_DEBUG_LEVEL
from .host import restart_service
from .config import load_config_file
from .runtime import PironmanRuntime

log = Logger(APP_NAME)
__package_name__ = __name__.split('.')[0]

pm_auto_version = None
try:
    pm_auto_version = metadata.version("pm_auto")
except metadata.PackageNotFoundError:
    pass

PMDashboard = None
try:
    from pm_dashboard.pm_dashboard import PMDashboard
    from pm_dashboard import __version__ as pm_dashboard_version
except ImportError:
    pass

class Pironman5:

    def __init__(self, config_path=CONFIG_PATH):
        self.peripherals = PERIPHERALS
        self.log = log

        # Load config
        # -----------------------------------------
        self.config = {
            'system': SYSTEM_DEFAULT_CONFIG,
        }
        self.config['system']['debug_level'] = DEFAULT_DEBUG_LEVEL

        self.config_path = config_path
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            config = self.upgrade_config(config)
            self.config = merge_dict(self.config, config)
        write_json_private(self.config_path, self.config)

        # Set debug level
        # -----------------------------------------
        _debug_level = self.config['system']['debug_level'].upper()
        if _debug_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            self.log.warning(f"Invalid debug level '{_debug_level}', using default '{DEFAULT_DEBUG_LEVEL}'")
            _debug_level = DEFAULT_DEBUG_LEVEL
        self.set_debug_level(_debug_level)

        # LOG HEADER
        log.info(f"")
        log.info(f"{'#'*60}")
        log.debug(f"Config path: {CONFIG_PATH}")
        log.info(f"Pironman5 Start")

        if 'enable_history' in self.config['system']:
            _p = set(self.peripherals)
            if self.config['system']['enable_history']:
                _p.add('history')
                _p.add('clear_history')
            else:
                if 'history' in _p:
                    _p.remove('history')
                if 'clear_history' in _p:
                    _p.remove('clear_history')
            self.peripherals = list(_p)

        self.history = None
        if self.config['system'].get('enable_history', False):
            history_path = self.config['system'].get(
                'history_db_path',
                '/opt/pironman5/history.sqlite3',
            )
            self.history = SQLiteHistory(history_path)
            self.history.initialize()
            self.history.apply_retention(self.config['system'].get('database_retention_days', 30))

        # init runtime and optional dashboard
        # -----------------------------------------
        device_info = {
            'name': NAME,
            'id': ID,
            'peripherals': self.peripherals,
            'version': pironman5_version,
            'app_name': APP_NAME,
            'config_path': self.config_path,
        }
        self.log.info(f"Pironman5 version: {pironman5_version}")
        self.log.info(f"Variant: {NAME} {PRODUCT_VERSION}")

        _config_json = json.dumps(redact_secrets(self.config), indent=4)
        self.log.info(f"Config:")
        for line in _config_json.splitlines():
            self.log.info(line)
        _device_info_json = json.dumps(device_info, indent=4)
        self.log.info(f"Device info:")
        for line in _device_info_json.splitlines():
            self.log.info(line)

        if pm_auto_version is None:
            self.log.info('PM Auto not installed; optional bridge modules remain unavailable')
        else:
            self.log.info(f"PM_Auto version: {pm_auto_version}")
        if PMDashboard is not None:
            self.log.info(f"PM_Dashboard version: {pm_dashboard_version}")

        self.runtime = PironmanRuntime(self.config['system'],
                                       peripherals=self.peripherals,
                                       device_info=device_info,
                                       event_map=EVENT_MAP,
                                       log=log)
        if PMDashboard is None:
            self.pm_dashboard = None
            self.log.info('PM Dashboard not installed; skipping optional dashboard startup')
        else:
            self.pm_dashboard = PMDashboard(device_info=device_info,
                                            database=ID,
                                            config=self.config,
                                            log=log)
            self.pm_dashboard.set_read_data(self.runtime.read)
            self.pm_dashboard.set_read_config(self.read_config)
            if 'send_email' in self.peripherals:
                self.pm_dashboard.set_test_smtp(self.runtime.test_smtp)
            self.pm_dashboard.set_on_config_changed(self.update_config)
            self.pm_dashboard.set_on_restart_service(restart_service)

    @log_error
    def read_config(self):
        return self.config

    @log_error
    def set_debug_level(self, level):
        self.log.setLevel(level)

    @log_error
    def upgrade_config(self, config):
        ''' upgrade old config to new config converting 'auto' to'system' '''
        if 'auto' in config:
            return {'system': config['auto']}
        return config

    @log_error
    def update_config(self, config):
        patch = {}
        if 'debug_level' in config['system']:
            level = config['system']['debug_level'].upper()
            self.set_debug_level(level)
            patch['debug_level'] = level
        pm_auto_patch = self.runtime.update_config(config['system'])
        patch.update(pm_auto_patch)
        if self.pm_dashboard:
            dashboard_patch = self.pm_dashboard.update_config(config['system'])
            patch.update(dashboard_patch)

        if len(patch) > 0:
            self.log.debug(f"Update config: {patch}")
            self.config['system'].update(patch)
            self.log.debug(f"New config: {json.dumps(redact_secrets(self.config), indent=4)}")
            write_json_private(self.config_path, self.config)

        return self.config

    @log_error
    def start(self):
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGABRT, self.signal_handler)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, self.reload_signal_handler)
        self.runtime.start()
        if self.pm_dashboard:
            self.pm_dashboard.start()
        while True:
            time.sleep(1)

    @log_error
    def stop(self):
        self.log.info('Stopping Pironman5')
        self.log.info('Stopping runtime')
        self.runtime.stop()
        if self.pm_dashboard:
            self.log.info('Stopping PmDashboard')
            self.pm_dashboard.stop()
        self.log.info('Pironman5 stopped')
        # Check if there's any thread still alive
        import threading
        for t in threading.enumerate():
            if t is not threading.main_thread():
                self.log.warning(f"Thread {t.name} is still alive")
        quit()

    @log_error
    def signal_handler(self, signum, frame):
        self.log.info(f'Received signal "{signal.strsignal(signum)}", cleaning up...')
        self.stop()

    @log_error
    def reload_config(self):
        self.log.info("Reloading config")
        config = self.upgrade_config(load_config_file(self.config_path))
        self.update_config(config)

    @log_error
    def reload_signal_handler(self, signum, frame):
        self.log.info(f'Received signal "{signal.strsignal(signum)}"')
        self.reload_config()
