#!/usr/bin/env python3
import argparse
import sys
import time
import threading
import os
import glob
import importlib
import subprocess
import grp
import shutil
import shlex

class ConfigTxt(object):
    DEFAULT_BOOT_FILE = "/boot/firmware/config.txt"
    BACKUP_BOOT_FILE = "/boot/config.txt"

    def __init__(self, file=None):
        # check if file exists
        self.__isready = True
        if file is None:
            if os.path.exists(self.DEFAULT_BOOT_FILE):
                self.file = self.DEFAULT_BOOT_FILE
            elif os.path.exists(self.BACKUP_BOOT_FILE):
                self.file = self.BACKUP_BOOT_FILE
            else:
                print("No config.txt file found.")
                self.__isready = False
                return
        else:
            self.file = file
            if not os.path.exists(file):
                print(f"config.txt not found at {file}")
                self.__isready = False
                return
        # read config file
        with open(self.file, 'r') as f:
            self.configs = f.read()
        self.configs = self.configs.split('\n')

    def isready(self):
        return self.__isready

    def remove(self, expected):
        for key in self.configs:
            if expected in key:
                self.configs.remove(key)
        return self.write_file()

    def comment(self, expected):
        for i in range(len(self.configs)):
            line = self.configs[i]
            if expected in line:
                self.configs[i] = '#' + line
        return self.write_file()

    def set(self, name, value=None, device="[all]"):
        '''
        device : "[all]", "[pi3]", "[pi4]" or other
        '''
        have_excepted = False
        for i in range(len(self.configs)):
            line = self.configs[i]
            if name in line:
                have_excepted = True
                tmp = name
                if value != None:
                    tmp += '=' + value
                if line == tmp:
                    return 1, line
                self.configs[i] = tmp
                break

        if not have_excepted:
            self.configs.append(device)
            tmp = name
            if value != None:
                tmp += '=' + value
            self.configs.append(tmp)
        return self.write_file()

    def write_file(self):
        try:
            content = '\n'.join(self.configs)
            with open(self.file, 'w') as f:
                f.write(content)
            return 0, content
        except Exception as e:
            return -1, e


class SF_Installer():
    WORK_DIR = '/opt/{name}'
    GIT_URL = None
    MAIN_GIT_URL = 'https://github.com/sunfounder/'
    BACKUP_GIT_URLS = {
        'github': 'https://github.com/sunfounder/', 
        'gitee': 'https://gitee.com/sunfounder/',
    }

    APT_DEPENDENCIES = [
        'python3-pip',
        'python3-venv',
        'git',
    ]

    PIP_DEPENDENCIES = [
        'pip',
        'setuptools',
        'build',
        'requests',
    ]

    SUDOER_PERMISSION = [
        "/usr/sbin/shutdown",
        "/usr/sbin/reboot",
        "/usr/sbin/poweroff",
        "/usr/sbin/halt",
        "/usr/bin/systemctl",
        "/usr/bin/lsblk",
    ]

    DEFAULT_GROUPS = [
        'video',
    ]

    DPKG_LOCK_FILES = [
        "/var/lib/dpkg/lock",
        "/var/lib/dpkg/lock-frontend",
        "/var/lib/apt/lists/lock",
    ]

    def __init__(self,
                name=None,
                friendly_name=None,
                description=None,
                work_dir=None,
                log_dir=None,):
        if name is None:
            print("Please specify a name for the software")
            sys.exit(1)
        else:
            self.name = name
        if friendly_name is None:
            self.friendly_name = name
        else:
            self.friendly_name = friendly_name
        if description is None:
            self.description = f'Installer for {self.friendly_name}'
        else:
            self.description = description
        if work_dir is None:
            self.work_dir = self.WORK_DIR.format(name=self.name)
        else:
            self.work_dir = work_dir
        if log_dir is None:
            self.log_dir = f'/var/log/{self.name}'
        else:
            self.log_dir = log_dir
        self.log_file = f'{self.log_dir}/{self.name}.log'

        self.groups = set(self.DEFAULT_GROUPS)
        self.build_dependencies = set()
        self.preflight_actions = []
        self.before_install_scripts = set()
        self.custom_apt_dependencies = set()
        self.custom_uninstall_pip_dependencies = set()
        self.custom_pip_dependencies = set()
        self.python_source = {}
        self.symlinks = set()
        self.config_txt = {}
        self.modules = set()
        self.service_files = set()
        self.bin_files = set()
        self.dtoverlays = set()
        self.after_install_scripts = set()
        self.venv_options = set()
        self.work_files = {}

        self.parser = argparse.ArgumentParser(description=description)
        self.parser.add_argument('--uninstall', action='store_true', help='Uninstall')
        self.parser.add_argument('--no-dep',
                                 action='store_true',
                                 help='Do not install dependencies')
        self.parser.add_argument('--skip-reboot',
                                 action='store_true',
                                 help='Skip reboot even needed')
        self.parser.add_argument('--plain-text',
                                 action='store_true',
                                 help='Plain text mode')
        self.parser.add_argument('--skip-auto-start',
                                    action='store_true',
                                    help='Skip auto start')
        self.parser.add_argument('--skip-config-txt',
                                    action='store_true',
                                    help='Skip config.txt')
        self.parser.add_argument('--skip-dtoverlay',
                                    action='store_true',
                                    help='Skip dtoverlay')
        self.parser.add_argument('--skip-modules',
                                    action='store_true',
                                    help='Skip probe modules')
        self.config_txt_handler = ConfigTxt()
        self.user = self.name
        self.errors = []
        self.is_running = False
        self.need_reboot = True
        self.args = None

        self.venv_path = f'{self.work_dir}/venv'
        self.venv_python = f'{self.venv_path}/bin/python3'
        self.venv_pip = f'{self.venv_path}/bin/pip3'
        self.custom_install = lambda: None

        self.version = self.get_version()

    def get_version(self):
        version_file = f'{self.name}/version.py'
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                for line in f:
                    if line.startswith('__version__'):
                        return line.split('=')[1].strip().strip("'")

    def update_settings(self, settings):
        if 'groups' in settings:
            self.groups.update(settings['groups'])
        if 'build_dependencies' in settings:
            self.build_dependencies.update(settings['build_dependencies'])
        if 'preflight_actions' in settings:
            for action in settings['preflight_actions']:
                if action not in self.preflight_actions:
                    self.preflight_actions.append(action)
        if 'run_scripts_before_install' in settings:
            self.before_install_scripts.update(settings['run_scripts_before_install'])
        if 'apt_dependencies' in settings:
            self.custom_apt_dependencies.update(settings['apt_dependencies'])
        if 'uninstall_pip_dependencies' in settings:
            self.custom_uninstall_pip_dependencies.update(settings['uninstall_pip_dependencies'])
        if 'pip_dependencies' in settings:
            self.custom_pip_dependencies.update(settings['pip_dependencies'])
        if 'python_source' in settings:
            self.python_source.update(settings['python_source'])
        if 'symlinks' in settings:
            self.symlinks.update(settings['symlinks'])
        if 'config_txt' in settings:
            self.config_txt.update(settings['config_txt'])
        if 'modules' in settings:
            self.modules.update(settings['modules'])
        if 'service_files' in settings:
            self.service_files.update(settings['service_files'])
        if 'bin_files' in settings:
            self.bin_files.update(settings['bin_files'])
        if 'dtoverlays' in settings:
            self.dtoverlays.update(settings['dtoverlays'])
        if 'run_scripts_after_install' in settings:
            self.after_install_scripts.update(settings['run_scripts_after_install'])
        if 'venv_options' in settings:
            self.venv_options.update(settings['venv_options'])
        if 'work_files' in settings:
            self.work_files.update(settings['work_files'])

    def set_config_txt(self, name="", value=""):
        msg = f"Setting config.txt: {name}={value}"
        print(" - %s... " % (msg), end='', flush=True)
        try:
            code, _ = self.config_txt_handler.set(name, value)
            if code == 0:
                self.need_reboot = True
                print('Done')
            else:
                print('Already')
        except Exception as e:
            print('\033[1;35mError\033[0m')
            self.errors.append("%s error:\n Error:%s" % (msg, e))

    def get_current_username(self):
        try:
            user = os.getlogin()  # can run at boot
        except:
            user = os.popen("echo ${SUDO_USER:-$(who -m | awk '{ print $1 }')}"
                            ).readline().strip()
        return user

    def run_command(self, cmd=""):
        p = subprocess.Popen(cmd,
                             shell=True,
                             executable="/bin/bash",
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             universal_newlines=True)
        p.wait()
        result = p.stdout.read()
        error = p.stderr.read()
        status = p.poll()
        return status, result, error

    @staticmethod
    def shell_join(args):
        return " ".join(shlex.quote(str(arg)) for arg in args)

    @staticmethod
    def asset_path(*parts):
        return os.path.join("pironman5", "assets", *parts)

    def spinner(self):
        char = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        i = 0
        while self.is_running:
            i = (i + 1) % len(char)
            sys.stdout.write('\033[?25l')  # cursor invisible
            sys.stdout.write(f'\r\033[36m{char[i]}\033[0m')
            sys.stdout.flush()
            time.sleep(0.1)

        sys.stdout.write(' \033[1D')
        sys.stdout.write('\033[?25h')  # cursor visible
        sys.stdout.flush()

    def do(self, msg="", cmd="", ignore_error=False):
        print(f"  {msg}", end='', flush=True)
        if not self.args.plain_text:
            self.is_running = True
            _thread = threading.Thread(target=self.spinner)
            _thread.daemon = True
            _thread.start()
        # process run
        status, result, error = self.run_command(cmd)
        if not self.args.plain_text:
            # at_work_tip stop
            self.is_running = False
            while _thread.is_alive():
                time.sleep(0.01)
        # status
        if status == 0:
            print(f'\r{self.SUCCESS}')
        else:
            if ignore_error:
                print(f'\r{self.SKIPPED}')
            else:
                print(f'\r{self.FAILED}')
                self.errors.append(
                    f"{self.FAILED} {msg} error:\n  Command: {cmd}\n  Status: {status}\n  Result: {result}\n  Error: {error}\n"
                )

    def print_title(self, title, end='\n', flush=False):
        if self.args.plain_text:
            print(f"\n{title}", end=end, flush=flush)
        else:
            print(f"\n\033[1;34m{title}\033[0m", end=end, flush=flush)

    @property
    def SUCCESS(self):
        if self.args.plain_text:
            return "✓"
        else:
            return "\033[32m✓\033[0m"

    @property
    def WARNING(self):
        if self.args.plain_text:
            return "⚠"
        else:
            return "\033[1;33m⚠\033[0m"

    @property
    def SKIPPED(self):
        if self.args.plain_text:
            return "→"
        else:
            return "\033[1;33m→\033[0m"

    @property
    def FAILED(self):
        if self.args.plain_text:
            return "✗"
        else:
            return "\033[1;35m✗\033[0m"

    def check_admin(self):
        if os.geteuid() != 0:
            print(f'{self.FAILED} This script must be run as root')
            sys.exit(1)

    def remove_work_dir(self):
        if not os.path.exists(self.work_dir):
            print(f"{self.SKIPPED} Work directory {self.work_dir} already removed, skip")
            return
        self.do('Remove work directory', self.shell_join(['rm', '-r', self.work_dir]))

    def install_python_source(self, name, url='./'):
        self.do(f'Uninstall old "{name}" package',
                self.shell_join([self.venv_pip, 'uninstall', '-y', name]))
        self.do(f'Install {name} from source',
                self.shell_join([self.venv_pip, 'install', url]))

    def is_group_exist(self, group: str) -> bool:
        """
        Check if group exists.
        
        Args:
            group: Group name.
        
        Returns:
            True if group exists, False otherwise.
        
        """
        try:
            grp.getgrnam(group)
            return True
        except KeyError:
            return False

    def add_user_to_group(self, user, group):
        _, users, _ = self.run_command(self.shell_join(['getent', 'group', group]))
        users = users.strip().split(':')
        if user in users:
            print(f'{self.SKIPPED} User "{user}" is already in group "{group}", skip')
        else:
            self.do(f'Add user "{user}" to group "{group}"', self.shell_join(['usermod', '-aG', group, user]))

    # Install Steps:

    def setup_user(self):
        # Create group if not exist
        self.print_title(f"Setup user {self.user}...")
        if self.run_command(self.shell_join(['getent', 'group', self.user]))[0] == 0:
            print(f'{self.SKIPPED} Group "{self.user}" already exists, skip')
        else:
            self.do(f'Create group "{self.user}"', self.shell_join(['groupadd', '-r', self.user]))

        # Create user if not exist
        if self.run_command(self.shell_join(['getent', 'passwd', self.user]))[0] == 0:
            print(f'{self.SKIPPED} User "{self.user}" already exists, skip')
        else:
            self.do(f'Create user "{self.user}"', self.shell_join(['useradd', '-r', '-g', self.user, '-s', '/sbin/nologin', '-d', f'/opt/{self.user}', '--no-create-home', self.user]))

        self.normalize_work_dir_permissions()

        # Add sudo permission to user
        if shutil.which('sudo'):
            sudoers_file = f'/etc/sudoers.d/{self.user}'
            sudoers_line = f'{self.user} ALL=(ALL) NOPASSWD: {", ".join(self.SUDOER_PERMISSION)}'
            printf_cmd = self.shell_join(['printf', '%s\n', sudoers_line])
            tee_cmd = self.shell_join(['tee', sudoers_file])
            sudoers_cmd = f"{printf_cmd} | {tee_cmd} > /dev/null"
            self.do(f'Add permission to user "{self.user}"', sudoers_cmd)
            self.do(f'Change sudoers file mode to 0440', self.shell_join(['chmod', '0440', sudoers_file]))
            self.do(f'Check sudoers file', self.shell_join(['visudo', '-c', '-f', sudoers_file]))
        else:
            print(f"{self.WARNING} Sudo is not exist, skip sudo permission setup")

    def normalize_work_dir_permissions(self):
        self.do('Create service home directory', self.shell_join(['mkdir', '-p', self.work_dir]))
        self.do(f'Change service home owner to "{self.user}"', self.shell_join(['chown', '-R', f'{self.user}:{self.user}', self.work_dir]))
        self.do(f'Change service home mode to 750', self.shell_join(['chmod', '750', self.work_dir]))
        self.do(
            'Change service home file modes to 640',
            self.shell_join(['find', self.work_dir, '-mindepth', '1', '-maxdepth', '1', '-type', 'f', '-exec', 'chmod', '640', '{}', '+']),
        )
        self.do(
            'Change service home directory modes to 750',
            self.shell_join(['find', self.work_dir, '-mindepth', '1', '-maxdepth', '1', '-type', 'd', '-exec', 'chmod', '750', '{}', '+']),
        )

    def add_user_to_groups(self):
        # Add groups to user
        groups = set()
        for group_name in self.groups:
            if not self.is_group_exist(group_name):
                print(f"{self.WARNING} Group '{group_name}' does not exist, use default group 'dialout'")
                group_name = 'dialout'
            groups.add(group_name)

        for group_name in groups:
            self.add_user_to_group(self.user, group_name)

    def get_dpkg_lock_holders(self):
        holders = []
        current_pid = str(os.getpid())

        for lock_file in self.DPKG_LOCK_FILES:
            if not os.path.exists(lock_file):
                continue
            status, result, _error = self.run_command(self.shell_join(['fuser', lock_file]))
            if status != 0 or not result.strip():
                continue
            for pid in result.split():
                if pid == current_pid:
                    continue
                process = "unknown"
                ps_status, ps_result, _ps_error = self.run_command(
                    self.shell_join(['ps', '-o', 'comm=', '-p', pid])
                )
                if ps_status == 0 and ps_result.strip():
                    process = os.path.basename(ps_result.strip().splitlines()[0])
                holders.append({
                    "lock_file": lock_file,
                    "pid": pid,
                    "process": process,
                })

        return holders

    def wait_for_dpkg(self, wait_interval=1, max_wait=3600):
        start_time = time.time()
        while True:
            holders = self.get_dpkg_lock_holders()
            if not holders:
                return
            elapsed = time.time() - start_time
            if elapsed >= max_wait:
                details = ", ".join(
                    f"{holder['lock_file']} held by {holder['process']}({holder['pid']})"
                    for holder in holders
                )
                raise RuntimeError(f"Timeout waiting for dpkg to become available: {details}")
            holder = holders[0]
            print(
                f"dpkg currently locked by \"{holder['process']}\"({holder['pid']}), waiting...",
                flush=True,
            )
            time.sleep(wait_interval)

    def run_preflight_actions(self):
        if len(self.preflight_actions) == 0:
            return
        self.print_title("Run installer preflight actions...")
        allowed_actions = {
            "install_lgpio": self.install_lgpio,
            "fix_kali_gpio_spi_groups": self.fix_kali_gpio_spi_groups,
        }
        for action in self.preflight_actions:
            if action not in allowed_actions:
                raise ValueError(f"Unknown preflight action: {action}")
            allowed_actions[action]()

    def install_lgpio(self):
        self.do(
            "Install LGPIO packages",
            self.shell_join([
                'env',
                'DEBIAN_FRONTEND=noninteractive',
                'apt-get',
                'install',
                '-y',
                'liblgpio-dev',
                'python3-lgpio',
            ]),
        )

    def is_kali_linux(self):
        try:
            with open("/etc/os-release", "r") as f:
                return "Kali" in f.read()
        except OSError:
            return False

    def fix_kali_gpio_spi_groups(self):
        if not self.is_kali_linux():
            print(f"{self.SKIPPED} Not Kali Linux, skip GPIO/SPI group fix")
            return
        for group in ["gpio", "spi"]:
            self.do(
                f'Ensure "{group}" system group exists',
                self.shell_join(['getent', 'group', group]) + " > /dev/null || " + self.shell_join(['groupadd', '-r', group]),
            )

    def install_build_dep(self):
        self.print_title("Install build dependencies...")
        self.do('Update package list', self.shell_join(['env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'update']))
        deps = [ *self.APT_DEPENDENCIES ]

        if self.build_dependencies is not None:
            deps += self.build_dependencies

        deps_display = " ".join(deps)
        msg = f'Install build dependencies: {deps_display}'
        width = int(os.environ.get('COLUMNS', 80))
        if len(msg) > width - 3:
            msg = msg[:width-3] + '...'
        self.do(msg, self.shell_join(['env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'install', '-y', *deps]))

    def run_scripts_before_install(self):
        if len(self.before_install_scripts) == 0:
            return
        self.print_title("Run scripts before install...")
        for script in self.before_install_scripts:
            self.do(f'Run scripts before install: {script}', self.shell_join(['bash', f'scripts/{script}']))

    def run_scripts_after_install(self):
        if len(self.after_install_scripts) == 0:
            return
        self.print_title("Run scripts after install...")
        for script in self.after_install_scripts:
            self.do(f'Run scripts after install: {script}', self.shell_join(['bash', f'scripts/{script}']))

    def install_apt_dep(self):
        if ('no_dep' in self.args and self.args.no_dep) or \
            len(self.custom_apt_dependencies) == 0:
            return
        self.print_title("Install APT dependencies...")

        deps = [ *self.custom_apt_dependencies ]
        deps_display = " ".join(deps)
        msg = f'Install APT dependencies: {deps_display}'
        width = int(os.environ.get('COLUMNS', 80))
        if len(msg) > width-3:
            msg = msg[:width-3] + '...'
        self.do(msg, self.shell_join(['env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'install', '-y', *deps]))

    def create_working_dir(self):
        self.print_title("Create working directory...")
        self.do('Create work directory', self.shell_join(['mkdir', '-p', self.work_dir]))
        self.do(f'Change work directory mode to 750', self.shell_join(['chmod', '750', self.work_dir]))
        self.do(f'Change work directory owner to "{self.user}"', self.shell_join(['chown', '-R', f'{self.user}:{self.user}', self.work_dir]))
        self.do('Create log directory', self.shell_join(['mkdir', '-p', self.log_dir]))
        self.do(f'Change log directory mode to 750', self.shell_join(['chmod', '750', self.log_dir]))
        self.do(f'Change log directory owner to "{self.user}"', self.shell_join(['chown', '-R', f'{self.user}:{self.user}', self.log_dir]))
        self.do(f'Create log file: "{self.log_file}"', self.shell_join(['touch', self.log_file]))
        self.do(f'Change log file mode to 640', self.shell_join(['chmod', '640', self.log_file]))
        self.do(f'Change log file owner to "{self.user}"', self.shell_join(['chown', f'{self.user}:{self.user}', self.log_file]))
        if os.path.exists(self.venv_path):
            self.do('Remove old virtual environment', self.shell_join(['rm', '-r', self.venv_path]))
        self.do('Create virtual environment', self.shell_join(['python3', '-m', 'venv', self.venv_path, *self.venv_options]))

    def write_work_files(self):
        if len(self.work_files) == 0:
            return
        self.print_title("Write work files...")
        for filename, content in self.work_files.items():
            destination = f"{self.work_dir}/{filename}"
            printf_cmd = self.shell_join(['printf', '%s', content])
            tee_cmd = self.shell_join(['tee', destination])
            self.do(f'Write work file: "{destination}"', f"{printf_cmd} | {tee_cmd} > /dev/null")
            self.do(f'Change work file owner to "{self.user}"', self.shell_join(['chown', f'{self.user}:{self.user}', destination]))
            self.do(f'Change work file mode to 640', self.shell_join(['chmod', '640', destination]))

    def uninstall_pip_dep(self):
        if ('no_dep' in self.args and self.args.no_dep) or \
            len(self.custom_uninstall_pip_dependencies) == 0:
            return
        deps = [ *self.custom_uninstall_pip_dependencies ]
        deps_display = " ".join(deps)
        self.print_title(f"Uninstall: {deps_display}")
        self.do(f'Uninstall {deps_display}',
                self.shell_join([self.venv_pip, 'uninstall', '-y', *deps]))

    def install_pip_dep(self):
        if ('no_dep' in self.args and self.args.no_dep) or \
            len(self.custom_pip_dependencies) == 0:
            return
        self.print_title("Install PIP dependencies...")
        deps = [ *self.PIP_DEPENDENCIES ]
        if self.custom_pip_dependencies is not None:
            deps += self.custom_pip_dependencies
        deps_display = " ".join(deps)
        # Install everything together make it faster
        self.do(f'Install {deps_display}',
                self.shell_join([self.venv_pip, 'install', '--upgrade', *deps]))
        # for dep in deps:
        #     self.do(f'Install {dep}', f'{self.venv_pip} install --upgrade {dep}')

    def check_git_url(self):
        self.print_title("Check git URL...")
        # Test if github url reachable
        venv_site_pkgs = f"{glob.glob(f'{self.venv_path}/lib/python*')[0]}/site-packages"
        sys.path.insert(0, venv_site_pkgs)  # add to front of path
        requests = importlib.import_module('requests')
        for name, url in self.BACKUP_GIT_URLS.items():
            try:
                requests.get(url)
                self.GIT_URL = url
                print(f'{self.SUCCESS} Use {name} as remote repository')
                return
            except requests.exceptions.RequestException:
                print(f'{self.WARNING} {name} is not reachable')
                continue
        else:
            print(f'{self.FAILED} None of these is reachable: {self.BACKUP_GIT_URLS}')
            sys.exit(1)

    def install_py_src_pkgs(self):
        if len(self.python_source) == 0:
            return
        self.print_title("Install Python source packages...")
        for package, url in self.python_source.items():
            url = url.replace(self.MAIN_GIT_URL, self.GIT_URL)
            self.install_python_source(package, url)

    def create_symlinks(self):
        if len(self.symlinks) == 0:
            return
        self.print_title("Create symlinks...")
        for script in self.symlinks:
            self.do(f'Create symbolic link: {self.venv_path}/bin/{script} -> /usr/local/bin/{script}',
                    self.shell_join(['ln', '-s', '-f', f'{self.venv_path}/bin/{script}', f'/usr/local/bin/{script}']))

    def setup_auto_start(self):
        if ('skip_auto_start' in self.args and self.args.skip_auto_start) or \
            (len(self.service_files) == 0 and len(self.bin_files) == 0):
            return
        self.print_title("Setup auto start...")
        for bin in self.bin_files:
            self.do('Copy binary file', self.shell_join(['cp', self.asset_path('bin', bin), '/usr/local/bin/']))
            self.do('Change binary file mode', self.shell_join(['chmod', '+x', f'/usr/local/bin/{bin}']))
        for service in self.service_files:
            self.do('Copy service file', self.shell_join(['cp', self.asset_path('bin', service), '/etc/systemd/system/']))
            self.do('Enable service', self.shell_join(['systemctl', 'enable', service]))
            self.do('Reload systemd', 'systemctl daemon-reload')

    def setup_config_txt(self):
        if ('skip_config_txt' in self.args and self.args.skip_config_txt) or \
            len(self.config_txt) == 0:
            return
        self.print_title("Setup config.txt...")
        for name, value in self.config_txt.items():
            self.set_config_txt(name, value)
        self.need_reboot = True

    def modules_probe(self):
        if ('skip_modules' in self.args and self.args.skip_modules) or \
            len(self.modules) == 0:
            return
        self.print_title("Probe modules...")
        modules = " ".join(shlex.quote(module) for module in sorted(self.modules))
        self.do(
            'Write module load config: "/etc/modules-load.d/pironman5.conf"',
            f"printf '%s\\n' {modules} | install -m 0644 -o root -g root /dev/stdin /etc/modules-load.d/pironman5.conf",
        )

    def copy_dtoverlay(self):
        # Copy device tree overlay
        if ('skip_dtoverlay' in self.args and self.args.skip_dtoverlay) or \
            len(self.dtoverlays) == 0:
            return
        self.print_title("Copy device tree overlay...")
        POSSIBLE_OVERLAY_PATHS = [
            '/boot/firmware/overlays',
            '/boot/overlays',
            '/boot/firmware/current/overlays',
        ]
        overlays_path = None
        for path in POSSIBLE_OVERLAY_PATHS:
            if os.path.exists(path):
                overlays_path = path
                break
        if overlays_path is None:
            self.errors.append(f"Device tree overlay directory {POSSIBLE_OVERLAY_PATHS} not found")
            return
        
        for overlay in self.dtoverlays:
            if overlay.startswith('http'):
                self.errors.append("Remote dtoverlay downloads are disabled; ship dtoverlays in pironman5/assets/overlays/")
                continue
            else:
                overlay_source = self.asset_path('overlays', overlay)
                if not os.path.exists(overlay_source):
                    self.errors.append(f"Device tree overlay file {overlay} not found")
                    continue
                self.do(
                    f'Install dtoverlay {overlay}',
                    self.shell_join([
                        'install',
                        '-m', '0644',
                        '-o', 'root',
                        '-g', 'root',
                        overlay_source,
                        f'{overlays_path}/{overlay}',
                    ]),
                )

        self.need_reboot = True

    def change_work_dir_owner(self):
        self.print_title("Fix work directory permission...")
        self.do(f'Change work directory mode to 750', self.shell_join(['chmod', '750', self.work_dir]))
        self.do(f'Change work directory owner to {self.user}', self.shell_join(['chown', '-R', f'{self.user}:{self.user}', self.work_dir]))

    # Uninstall Steps:

    def remove_symlinks(self):
        if len(self.symlinks) == 0:
            return
        self.print_title("Remove symlinks...")
        for link in self.symlinks:
            self.do(f'Remove symbolic link: {link}',
                    self.shell_join(['rm', '-f', f'/usr/local/bin/{link}']))

    def uninstall_scripts(self):
        if len(self.before_install_scripts) == 0:
            return
        self.print_title("Uninstall scripts...")
        for script in self.before_install_scripts:
            self.do(f'Uninstall script: {script}', self.shell_join(['bash', f'scripts/{script}', '--uninstall']))

    def remove_auto_start(self):
        if len(self.service_files) == 0 and len(self.bin_files) == 0:
            return
        self.print_title("Remove auto start...")
        for bin in self.bin_files:
            self.do('Remove binary file', self.shell_join(['rm', '-f', f'/usr/local/bin/{bin}']))
        for service in self.service_files:
            if not os.path.exists(f'/etc/systemd/system/{service}'):
                self.errors.append(f"{self.SKIPPED} Service file {service} not found, skip")
                continue
            self.do('Stop service', self.shell_join(['systemctl', 'stop', service]))
            self.do('Disable service', self.shell_join(['systemctl', 'disable', service]))
            self.do('Remove service file', self.shell_join(['rm', '-f', f'/etc/systemd/system/{service}']))
        self.do('Reload systemd', 'systemctl daemon-reload')

    def remove_dtoverlay(self):
        if len(self.dtoverlays) == 0:
            return
        
        self.print_title("Remove device tree overlay...")
        OVERLAY_PATH_DEFAULT = '/boot/overlays'
        OVERLAY_PATH_BACKUP = '/boot/firmware/overlays'
        overlays_path = OVERLAY_PATH_DEFAULT
        if not os.path.exists(overlays_path):
            overlays_path = OVERLAY_PATH_BACKUP
            if not os.path.exists(overlays_path):
                self.errors.append(f"{self.SKIPPED} Device tree overlay directory {OVERLAY_PATH_DEFAULT} or {OVERLAY_PATH_BACKUP} not found")
                return
        
        for overlay in self.dtoverlays:
            # if it's a online dtoverlay, skip it
            if overlay.startswith('http'):
                overlay = overlay.split('/')[-1]
            if not os.path.exists(f'{overlays_path}/{overlay}'):
                self.errors.append(f"{self.SKIPPED} Device tree overlay {overlay} not found, skip")
                continue
            self.do(f'Remove dtoverlay {overlay}', self.shell_join(['rm', f'{overlays_path}/{overlay}']))
            self.need_reboot = True

    def remove_logs(self):
        self.print_title("Remove logs...")
        self.do('Remove logs', self.shell_join(['rm', '-rf', self.log_dir]), ignore_error=True)

    def reboot_prompt(self):
        self.print_title("Reboot to apply the changes? (Y/N): ", end='')
        while True:
            key = input()
            if key == 'Y' or key == 'y':
                self.print_title(f'Reboot')
                self.run_command('reboot')
            elif key == 'N' or key == 'n':
                self.print_title(f'Canceled')
                return False
            else:
                print(f"{self.FAILED} Please enter Y or N: ", end='')
                continue

    def cleanup(self):
        self.do(f'Remove build', self.shell_join(['rm', '-r', './build']), ignore_error=True)

    def install(self):
        self.print_title(f"Installing {self.friendly_name} {self.version}")
        self.wait_for_dpkg()
        self.install_build_dep()
        self.run_preflight_actions()
        self.run_scripts_before_install()
        self.install_apt_dep()
        self.setup_user()
        self.add_user_to_groups()
        self.create_working_dir()
        self.write_work_files()
        self.uninstall_pip_dep()
        self.install_pip_dep()
        self.check_git_url()
        self.install_py_src_pkgs()
        self.create_symlinks()
        self.setup_auto_start()
        self.setup_config_txt()
        self.modules_probe()
        self.copy_dtoverlay()
        self.custom_install()
        self.change_work_dir_owner()
        self.run_scripts_after_install()
        self.print_title("Finished")

    def uninstall(self):
        self.print_title(f"Uninstall for {self.friendly_name}")
        self.remove_symlinks()
        self.uninstall_scripts()
        self.remove_auto_start()
        self.remove_work_dir()
        self.remove_dtoverlay()
        self.remove_logs()

    def main(self):
        self.check_admin()
        if self.args is None:
            self.args = self.parser.parse_args()
        try:
            if self.args.uninstall:
                self.uninstall()
            else:
                self.install()
        except KeyboardInterrupt:
            self.print_title("\n\nCanceled.")
        finally:
            sys.stdout.write(' \033[1D')
            sys.stdout.write('\033[?25h')  # cursor visible
            sys.stdout.flush()
            self.print_title('Cleanup')
            self.cleanup()
            if len(self.errors) == 0:
                if self.need_reboot and not self.args.skip_reboot:
                    self.reboot_prompt()
            else:
                print(f"\n\n{self.FAILED} Error happened in install process:")
                for error in self.errors:
                    print(error)
                print(
                    "Try to fix it yourself, or contact service@sunfounder.com with this message"
                )
                sys.exit(1)
