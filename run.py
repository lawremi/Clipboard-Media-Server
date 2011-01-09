from clipboardms.server import ClipboardMediaServer
from dbus.mainloop.glib import DBusGMainLoop
from gobject import MainLoop

DBusGMainLoop(set_as_default=True)

server = ClipboardMediaServer()

loop = MainLoop()
loop.run()
