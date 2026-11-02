"""App-owned preferences; tokens and vault keys only use the system keyring."""
import base64
import json
import os
from pathlib import Path
import gi
gi.require_version('Secret','1')
from gi.repository import Secret
from cache import atomic_write

SCHEMA=Secret.Schema.new('com.neg-zero.Galeria.Account',Secret.SchemaFlags.NONE,
                         {'identity':Secret.SchemaAttributeType.STRING,'kind':Secret.SchemaAttributeType.STRING})
LEGACY_SCHEMA=Secret.Schema.new('io.github.gallery.Account',Secret.SchemaFlags.NONE,
                         {'identity':Secret.SchemaAttributeType.STRING,'kind':Secret.SchemaAttributeType.STRING})


def secret_get(identity,kind):
    attributes={'identity':identity,'kind':kind}
    value=Secret.password_lookup_sync(SCHEMA,attributes,None)
    if value is None:
        value=Secret.password_lookup_sync(LEGACY_SCHEMA,attributes,None)
        if value is not None:secret_put(identity,kind,value)
    return value


def secret_put(identity,kind,value):
    return Secret.password_store_sync(SCHEMA,{'identity':identity,'kind':kind},Secret.COLLECTION_DEFAULT,'Galeria '+kind,value,None)


def secret_clear(identity,kind):
    attributes={'identity':identity,'kind':kind}
    new=Secret.password_clear_sync(SCHEMA,attributes,None)
    old=Secret.password_clear_sync(LEGACY_SCHEMA,attributes,None)
    return new or old


def vault_key(identity):
    value=secret_get(identity,'vault')
    if value:return base64.b64decode(value)
    key=os.urandom(32)
    if not secret_put(identity,'vault',base64.b64encode(key).decode()):raise RuntimeError('The system keyring is unavailable.')
    return key


# Keep the existing storage namespace so the rename preserves libraries and sync rules.
PREFERENCES=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'gallery'/'library.json'


def preferences_read():
    try:return json.loads(PREFERENCES.read_text())
    except (OSError,ValueError):return {}


def preferences_write(value):atomic_write(PREFERENCES,json.dumps(value).encode())
