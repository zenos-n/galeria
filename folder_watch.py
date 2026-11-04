"""Event-driven recursive monitors for enabled upload rules, in a private context."""
import json,os,threading
from pathlib import Path
from gi.repository import Gio,GLib
from library import IMAGE_TYPES,VIDEO_TYPES


class FolderWatch:
    def __init__(self,config,changed):
        self.config=Path(config);self.changed=changed;self.monitors={};self.pending=None
        self.context=GLib.MainContext.new();self.loop=GLib.MainLoop.new(self.context,False)
        self.ready=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True,name='galeria-folder-watch');self.thread.start()

    def directories(self):
        paths={self.config.parent}
        try:config=json.loads(self.config.read_text())
        except (OSError,ValueError):config={}
        for account in config.get('accounts',{}).values():
            if not account.get('enabled'):continue
            for rule in account.get('folders',[]):
                if not rule.get('enabled',True):continue
                root=Path(rule['path'])
                if not root.is_absolute():continue
                ancestor=root.parent
                while not ancestor.exists() and ancestor!=ancestor.parent:ancestor=ancestor.parent
                paths.add(ancestor)
                for directory,dirs,_ in os.walk(root,followlinks=False):
                    paths.add(Path(directory));depth=len(Path(directory).relative_to(root).parts)
                    dirs[:]=[name for name in dirs if not (Path(directory)/name).is_symlink()]
                    if not rule.get('recursive',True) or rule.get('max_depth',0) and depth>=int(rule['max_depth']):dirs.clear()
        return paths

    def rebuild(self):
        paths=self.directories()
        for path in set(self.monitors)-paths:self.monitors.pop(path).cancel()
        for path in paths-set(self.monitors):
            try:
                monitor=Gio.File.new_for_path(str(path)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES,None)
                monitor.connect('changed',self.event);self.monitors[path]=monitor
            except GLib.Error:pass  # The service's infrequent recovery pass covers unavailable monitors.

    def event(self,monitor,file,other,event):
        names=[Path(value.get_path()) for value in (file,other) if value and value.get_path()]
        structural=any(path.is_dir() or path in self.monitors for path in names)
        relevant=structural or self.config in names or any(path.suffix.lower() in IMAGE_TYPES|VIDEO_TYPES for path in names)
        if not relevant:return
        if self.pending:self.pending.destroy()
        self.pending=GLib.timeout_source_new(250)
        def notify(*_):
            self.pending=None;self.rebuild();self.changed();return False
        self.pending.set_callback(notify);self.pending.attach(self.context)

    def run(self):
        self.context.push_thread_default()
        try:self.rebuild();self.ready.set();self.loop.run()
        finally:
            if self.pending:self.pending.destroy()
            for monitor in self.monitors.values():monitor.cancel()
            self.monitors.clear();self.context.pop_thread_default()

    def close(self):self.loop.quit();self.thread.join(timeout=3)
