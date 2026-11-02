from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from library import scan_folders
import session_store


class IdentityTests(unittest.TestCase):
    def test_legacy_session_and_vault_keys_remain_available_after_rename(self):
        with patch.object(session_store.Secret,'password_lookup_sync',side_effect=[None,'existing-key']) as lookup,patch.object(session_store,'secret_put') as store:
            self.assertEqual(session_store.secret_get('account','vault'),'existing-key')
            self.assertIs(lookup.call_args_list[1].args[0],session_store.LEGACY_SCHEMA)
            store.assert_called_once_with('account','vault','existing-key')
        with patch.object(session_store.Secret,'password_clear_sync',return_value=True) as clear:
            self.assertTrue(session_store.secret_clear('account','session'))
            self.assertEqual(clear.call_count,2)

    def test_desktop_open_accepts_explicit_files_and_skips_unsupported_or_links(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);photo=root/'photo.jpg';photo.write_bytes(b'photo')
            linked=root/'linked.jpg';linked.symlink_to(photo)
            other=root/'notes.txt';other.write_text('text')
            items,errors=scan_folders([str(photo),str(other),str(linked)])
            self.assertEqual([item.filename for item in items],['photo.jpg'])
            self.assertEqual(photo.read_bytes(),b'photo')


if __name__=='__main__':unittest.main()
