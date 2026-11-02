"""Immich PIN elevation and encrypted device copies of locked media."""
import json
import hashlib
import threading
import time
from urllib.parse import quote
from urllib.request import Request
from gi.repository import Adw, Gtk, GLib
from cache import MediaCache
from session_store import vault_key
from library import LibraryError


def unlock_folder(window,after=None):
    if not window.client:
        window.login();return
    client=window.client
    dialog=Adw.Dialog(title='Unlock locked folder',content_width=420,content_height=440)
    toolbar=Adw.ToolbarView();toolbar.add_top_bar(Adw.HeaderBar())
    page=Adw.PreferencesPage()
    group=Adw.PreferencesGroup(title='Unlock your photos')
    method=Adw.ComboRow(title='Unlock with',model=Gtk.StringList.new(['Immich PIN','Account password']))
    secret=Adw.PasswordEntryRow(title='PIN')
    method.connect('notify::selected',lambda *_:secret.set_title('Account password' if method.get_selected() else 'PIN'))
    sync=Adw.SwitchRow(title='Keep encrypted copies on this device',active=window.preferences.get('vault_sync',True),
                       subtitle='Files and thumbnails are encrypted. The system keyring protects the key.')
    for row in (method,secret,sync):group.add(row)
    page.add(group)
    actions=Adw.PreferencesGroup();feedback=Gtk.Label(wrap=True,margin_top=12,margin_bottom=12)
    unlock=Gtk.Button(label='Unlock',css_classes=['suggested-action'],margin_top=10,margin_bottom=10)
    actions.add(unlock);actions.add(feedback);page.add(actions)
    def submit(_):
        value=secret.get_text();password=bool(method.get_selected());keep=sync.get_active()
        if not value or not password and (len(value)!=6 or not value.isdigit()):
            feedback.set_label('Enter your six-digit Immich PIN.');return
        secret.set_text('');unlock.set_sensitive(False);feedback.set_label('Unlocking…')
        def work():
            try:key=vault_key(client.identity) if keep else None
            except Exception:raise LibraryError('The system keyring is unavailable. Disable device copies to view without saving.') from None
            client.unlock(value,password)
            return MediaCache(client.identity+'|locked|'+hashlib.sha256(key).hexdigest(),key=key,budget=None) if key else None
        def done(vault):
            window.data_generation+=1
            window.pending_images.clear()
            window.vault=vault
            window.texture_cache.clear()
            window.preferences['vault_sync']=keep;window.save_preferences()
            window.sync_cancel=threading.Event()
            dialog.close()
            after() if after else window.search_library()
            window.lock_button.set_visible(True)
            GLib.timeout_add_seconds(5,window.check_locked_expiry)
            if vault and not after:sync_locked(window,client,vault)
        def failed(message):
            unlock.set_sensitive(True);feedback.set_label(message)
        window.background(work,done,failed)
    unlock.connect('clicked',submit);toolbar.set_content(page);dialog.set_child(toolbar)
    window.dialog=dialog;dialog.present(window)


def sync_locked(window,client,vault):
    cancel=window.sync_cancel
    def work():
        page=1;items=[]
        while not cancel.is_set():
            batch,next_page=client.search({'visibility':'locked'},page=page)
            items.extend(batch)
            if not next_page:break
            page=int(next_page)
        if cancel.is_set():return None
        vault.put('index',json.dumps([item.metadata for item in items]).encode())
        for count,item in enumerate(items):
            if cancel.is_set():return None
            revision=item.metadata.get('checksum') or item.metadata.get('updatedAt','')
            key='original:'+item.id+revision
            if not vault.has(key):
                request=Request(client.base+'/assets/'+quote(item.id,safe='')+'/original',headers={'Authorization':'Bearer '+client.token})
                with client.http.open(request,timeout=20) as response:vault.sync_encrypted(key,response,cancel)
            client.image_bytes(item,vault=vault)
            if count%10==0:
                GLib.idle_add(window.lock_button.set_tooltip_text,f'Saving encrypted copies · {count+1} / {len(items)}')
        return len(items)
    def done(count):
        window.lock_button.set_tooltip_text('Lock folder')
        if count is not None:window.notice(f'{count} items saved as encrypted device copies.')
    window.background(work,done,lambda message:window.notice('Encrypted sync stopped: '+message))
