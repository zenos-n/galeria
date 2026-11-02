"""Session-bus controls for the GNOME helper; no media or credentials cross it."""
import threading
from gi.repository import Gio,GLib
from sync_service import read_config,wake_service,install_service,command,UNIT
from library import LibraryError

INTERFACE='com.neg_zero.Galeria.Control1'
OBJECT_PATH='/com/neg_zero/Galeria/Control1'
XML='''<node><interface name="com.neg_zero.Galeria.Control1">
<method name="Show"/><method name="FolderSync"/><method name="SyncNow"/><method name="Quit"/>
<method name="SetBackground"><arg name="enabled" type="b" direction="in"/></method>
<property name="Background" type="b" access="read"/><property name="KeepRunning" type="b" access="read"/>
<property name="SyncEnabled" type="b" access="read"/><property name="Busy" type="b" access="read"/>
<property name="Status" type="s" access="read"/>
</interface></node>'''


class DesktopControl:
    def __init__(self,app,connection):
        self.app=app;self.connection=connection;self.registration=0;self.timer=0;self.busy=False;self.previous={};self.closed=False
        if connection:
            info=Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
            self.registration=connection.register_object(OBJECT_PATH,info,self.call,self.property,None)
            self.timer=GLib.timeout_add_seconds(2,self.emit)

    def state(self):
        accounts=list(read_config().get('accounts',{}).values())
        enabled=any(value.get('enabled') and value.get('folders') for value in accounts)
        configured=any(value.get('folders') for value in accounts)
        visible=bool(self.app.window and self.app.window.get_visible())
        return {'Background':self.app.background_enabled and not visible,'KeepRunning':self.app.background_enabled,
                'SyncEnabled':enabled,'Busy':self.busy,
                'Status':'Folder sync enabled' if enabled else 'Folder sync paused' if configured else 'No sync folders configured'}

    def variants(self):return {key:GLib.Variant('s' if isinstance(value,str) else 'b',value) for key,value in self.state().items()}

    def property(self,_connection,_sender,_path,_interface,name):return self.variants().get(name)

    def emit(self):
        if self.closed:return False
        state=self.state()
        if self.connection and state!=self.previous:
            self.connection.emit_signal(None,OBJECT_PATH,'org.freedesktop.DBus.Properties','PropertiesChanged',GLib.Variant('(sa{sv}as)',(INTERFACE,self.variants(),[])))
            self.previous=state
        return True

    def call(self,_connection,_sender,_path,_interface,method,parameters,invocation):
        if method=='SyncNow':
            if self.busy:
                invocation.return_dbus_error(INTERFACE+'.Busy','A sync request is already in progress.');return
            if not self.state()['SyncEnabled']:
                invocation.return_dbus_error(INTERFACE+'.NotConfigured','Enable Background uploads in Folder sync first.');return
            self.busy=True;self.emit()
            def work():
                error=None
                try:
                    if command(['systemctl','--user','is-active','--quiet',UNIT],check=False).returncode:install_service()
                    else:wake_service()
                except Exception as failure:error=str(failure) if isinstance(failure,LibraryError) else 'Could not request folder sync.'
                def done():
                    self.busy=False
                    if error:invocation.return_dbus_error(INTERFACE+'.Failed',error)
                    else:invocation.return_value(None)
                    self.emit();return False
                GLib.idle_add(done)
            threading.Thread(target=work,daemon=True).start();return
        if method=='Show':self.app.activate()
        elif method=='FolderSync':self.app.open_folder_sync()
        elif method=='SetBackground':self.app.set_background(parameters.unpack()[0],persist=True)
        elif method=='Quit':GLib.idle_add(self.app.force_quit)
        else:invocation.return_dbus_error('org.freedesktop.DBus.Error.UnknownMethod','Unknown Galeria method.');return
        invocation.return_value(None);self.emit()

    def close(self):
        self.closed=True
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        if self.registration:self.connection.unregister_object(self.registration);self.registration=0
