"""App-owned preferences; tokens and vault keys only use the system keyring."""
import base64
import json
import os
from pathlib import Path
import gi
gi.require_version('Secret','1')
from gi.repository import Secret
from cache import atomic_write

SCHEMA=Secret.Schema.new('io.github.gallery.Account',Secret.SchemaFlags.NONE,
                         {'identity':Secret.SchemaAttributeType.STRING,'kind':Secret.SchemaAttributeType.STRING})


def secret_get(identity,kind):
    return Secret.password_lookup_sync(SCHEMA,{'identity':identity,'kind':kind},None)


def secret_put(identity,kind,value):
    return Secret.password_store_sync(SCHEMA,{'identity':identity,'kind':kind},Secret.COLLECTION_DEFAULT,'Gallery '+kind,value,None)


def vault_key(identity):
    value=secret_get(identity,'vault')
    if value:return base64.b64decode(value)
    key=os.urandom(32)
    if not secret_put(identity,'vault',base64.b64encode(key).decode()):raise RuntimeError('The system keyring is unavailable.')
    return key


PREFERENCES=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'gallery'/'library.json'


def preferences_read():
    try:return json.loads(PREFERENCES.read_text())
    except (OSError,ValueError):return {}


def preferences_write(value):atomic_write(PREFERENCES,json.dumps(value).encode())
