import configparser
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from library import LibraryError
from startup import LoginStartup


class StartupTests(unittest.TestCase):
    def test_login_launcher_is_background_only_and_removable(self):
        with TemporaryDirectory() as root,patch.dict(os.environ,{'XDG_CONFIG_HOME':root+'/config','XDG_STATE_HOME':root+'/state'}):
            startup=LoginStartup('/tmp/a folder/galeria')
            self.assertFalse(startup.enabled());startup.set_enabled(True)
            parser=configparser.ConfigParser(interpolation=None);parser.read(startup.path)
            self.assertEqual(parser['Desktop Entry']['Exec'],'"/tmp/a folder/galeria" --background')
            self.assertTrue(startup.enabled());self.assertEqual(startup.path.stat().st_mode&0o777,0o600)
            startup.set_enabled(False);self.assertFalse(startup.enabled());self.assertFalse(startup.path.exists())

    def test_managed_launcher_cannot_be_overwritten(self):
        with TemporaryDirectory() as root,patch.dict(os.environ,{'XDG_CONFIG_HOME':root}):
            startup=LoginStartup('/tmp/galeria');startup.path.parent.mkdir(parents=True)
            startup.path.symlink_to('/nix/store/managed-startup/galeria.desktop')
            self.assertTrue(startup.managed())
            with self.assertRaises(LibraryError):startup.set_enabled(False)
            self.assertTrue(startup.path.is_symlink())


if __name__=='__main__':unittest.main()
