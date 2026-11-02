"""Writable, opt-in desktop-login startup; managed launchers remain authoritative."""
import configparser
import os
from pathlib import Path
import subprocess
import threading
from cache import atomic_write
from library import LibraryError

APP_ID='com.neg-zero.Galeria'


def launcher():
    source=Path(__file__).resolve()
    return source.parents[2]/'bin/galeria' if str(source).startswith('/nix/store/') else source.parent/'run'


class LoginStartup:
    def __init__(self,executable=None):
        self.executable=Path(executable or launcher())
        self.path=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'autostart'/(APP_ID+'.desktop')
        self.root=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'gallery'/'login-runtime'
        self.lock=threading.Lock()

    def managed(self):return self.path.is_symlink() and str(self.path.resolve()).startswith('/nix/store/')

    def enabled(self):
        parser=configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(self.path.read_text())
            return not parser.getboolean('Desktop Entry','Hidden',fallback=False)
        except (OSError,ValueError,configparser.Error):return False

    def set_enabled(self,enabled):
        with self.lock:self._write(enabled)

    def refresh(self):
        with self.lock:
            if self.enabled() and not self.managed():self._write(True)

    def _write(self,enabled):
        if self.managed():raise LibraryError('Startup is controlled by your ZenOS configuration.')
        if not enabled:
            self.path.unlink(missing_ok=True)
            if self.root.is_symlink():self.root.unlink()
            return
        value=str(self.executable)
        if not self.executable.is_absolute() or any(char in value for char in '\n\r\x00'):raise LibraryError('The application launcher path is invalid.')
        if value.startswith('/nix/store/'):
            self.root.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            if self.root.is_symlink():self.root.unlink()
            result=subprocess.run(['nix-store','--add-root',str(self.root),'--indirect','--realise',str(self.executable.parents[1])],capture_output=True,timeout=30)
            if result.returncode:raise LibraryError('Could not retain the login launcher. Startup was not changed.')
        escaped=value.replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
        text='[Desktop Entry]\nType=Application\nName=Galeria\nExec="'+escaped+'" --background\nIcon='+APP_ID+'\nTerminal=false\nX-GNOME-Autostart-enabled=true\n'
        atomic_write(self.path,text.encode())
