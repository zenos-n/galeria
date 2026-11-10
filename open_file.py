"""Check a device original before offering to save it from focus view."""
import threading
from gi.repository import Adw,GLib
from upload_media import check_file


class OpenFileExit:
    def __init__(self,viewer):
        self.viewer=viewer;self.dialog=None;self.busy=False;self.resolved=False
        self.cancel=threading.Event()

    def close(self):
        self.cancel.set()
        if self.dialog:self.dialog.close();self.dialog=None

    def confirm(self,leave):
        viewer=self.viewer;window=viewer.window;client=window.client
        if self.resolved or not client:return False
        if self.busy or self.dialog:return True
        item=viewer.source.media_item;generation=window.data_generation
        def current():return window.viewer is viewer and window.client is client and window.data_generation==generation and not self.cancel.is_set()
        def subtitle(value=None):viewer.title.set_subtitle(value or item.created.strftime('%d %B %Y'))
        def continue_without_prompt():
            self.resolved=True;leave()
        def prompt(checked=None,message=None):
            if not current():return
            self.busy=False;subtitle()
            if checked and checked[2].get('assetId'):continue_without_prompt();return
            if checked and checked[2].get('action')!='accept':
                checked=None;message='Immich did not accept this file.'
            dialog=Adw.AlertDialog(heading='Save to Immich?' if checked else 'Could not check Immich',
                body=f'Save a copy of “{item.filename}” to your Immich library? The original stays on this device.' if checked else message)
            dialog.add_response('cancel','Cancel');dialog.add_response('discard','Don’t Save')
            dialog.add_response('save','Save' if checked else 'Retry')
            dialog.set_close_response('cancel');dialog.set_default_response('cancel')
            dialog.set_response_appearance('save',Adw.ResponseAppearance.SUGGESTED)
            self.dialog=dialog
            def respond(_dialog,response):
                self.dialog=None
                def proceed():
                    if not current():return False
                    if response=='discard':continue_without_prompt()
                    elif response=='save' and not checked:self.confirm(leave)
                    elif response=='save':
                        from import_ui import start_upload
                        self.busy=True;subtitle('Saving to Immich…')
                        def finished(success):
                            self.busy=False;subtitle()
                            if success and current():continue_without_prompt()
                        if not start_upload(window,prepared=(item,checked,viewer.stage.image.get_paintable()),finished=finished):finished(False)
                    return False
                GLib.idle_add(proceed)
            dialog.connect('response',respond);dialog.present(window)
        self.busy=True;subtitle('Checking Immich…')
        window.background(lambda:check_file(client,item.path,self.cancel),prompt,lambda message:prompt(message=message))
        return True
