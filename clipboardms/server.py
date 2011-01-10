import dbus
import dbus.service
import gtk
import gobject
import gio
import urllib
import os.path

MEDIA_CONTAINER_IFACE = 'org.gnome.UPnP.MediaContainer2'
MEDIA_ITEM_IFACE = 'org.gnome.UPnP.MediaItem2'
MEDIA_OBJECT_IFACE = 'org.gnome.UPnP.MediaObject2'

MIME_TYPES = {
    '.avi': 'video/x-msvideo',
    '.mp4': 'video/mp4',
    '.mkv': 'video/x-matroska'
    }

class MediaObjectMixin(dbus.service.Object):

    def get_properties(self, iface):
        if iface == MEDIA_OBJECT_IFACE:
            return {
                'DisplayName': self.display_name,
                'Parent': self.parent,
                'Type': self.type,
                'Path': self.path
                }
        else:
            return {}

    @dbus.service.method(dbus.PROPERTIES_IFACE,
                         in_signature='ss', out_signature='v')
    def Get(self, iface, name):
        return self.get_properties(iface)[name]
        
    @dbus.service.method(dbus.PROPERTIES_IFACE,
                         in_signature='s', out_signature='a{sv}')
    def GetAll(self, iface):
        return dbus.Dictionary(self.get_properties(iface), signature='sv')

    def get_all_properties(self):
        return self.get_properties(MEDIA_OBJECT_IFACE)
    
class MediaContainerMixin(MediaObjectMixin):

    def get_children(self):
        """Return lists of child items and containers."""
        raise NotImplementedError

    def list_child_properties(self, objects, offset, maxCount, filt):
        objects = objects[offset:(offset + maxCount)]
        return dbus.Array([x.get_all_properties() for x in objects],
                          signature='a{sv}')
    
    @dbus.service.method(MEDIA_CONTAINER_IFACE,
                         in_signature='uuas', out_signature='aa{sv}')
    def ListChildren(self, offset, maxCount, filt):
        items, containers = self.get_children()
        return self.list_child_properties(items + containers, offset, maxCount,
                                          filt)
        
    @dbus.service.method(MEDIA_CONTAINER_IFACE,
                         in_signature='uuas', out_signature='aa{sv}')
    def ListContainers(self, offset, maxCount, filt):
        return self.list_child_properties(self.get_children()[1], offset,
                                          maxCount, filt)

    @dbus.service.method(MEDIA_CONTAINER_IFACE,
                         in_signature='uuas', out_signature='aa{sv}')
    def ListItems(self, offset, maxCount, filt):
        return self.list_child_properties(self.get_children()[0], offset,
                                          maxCount, filt)
        
    def get_properties(self, iface):
        if iface == MEDIA_CONTAINER_IFACE:
            items, containers = self.get_children()
            return {
                'ItemCount': dbus.UInt32(len(items)),
                'ContainerCount': dbus.UInt32(len(containers)),
                'ChildCount': dbus.UInt32(len(items) + len(containers)),
                'Searchable': bool(self.searchable)
                }
        else:
            return super(MediaContainerMixin, self).get_properties(iface)

    def get_all_properties(self):
        props = self.get_properties(MEDIA_CONTAINER_IFACE)
        props.update(super(MediaContainerMixin, self).get_all_properties())
        return props
        
    @dbus.service.signal(MEDIA_CONTAINER_IFACE, signature='')
    def Updated(self):
        pass



class MediaItemMixin(MediaObjectMixin):

    def get_details(self):
        """Return item details"""
        raise NotImplementedError

    def get_properties(self, iface):
        if iface == MEDIA_ITEM_IFACE:
            props = { 'URLs': dbus.Array(self.urls, signature='s') }
            props.update(self.get_details())
            return props
        else:
            return super(MediaItemMixin, self).get_properties(iface)

    def get_all_properties(self):
        props = self.get_properties(MEDIA_ITEM_IFACE)
        props.update(super(MediaItemMixin, self).get_all_properties())
        return props


class ClipboardMediaServer(MediaContainerMixin):
    def __init__(self, appname = "clipboard", clipboard_name = "CLIPBOARD"):
        self.path = '/org/gnome/UPnP/MediaServer2/%s' % appname
        self.bus = dbus.SessionBus()
        super(ClipboardMediaServer, self).__init__(self.bus,
                                                   object_path=self.path)
        self.bus_name = dbus.service.BusName(
            'org.gnome.UPnP.MediaServer2.%s' % appname, self.bus)
        
        self.display_name = appname
        self.type = 'container'
        self.searchable = False
        self.clipboard = gtk.Clipboard(selection = clipboard_name)
        self.items = []
        self.last_text = None
        
        gobject.timeout_add(1000, self.check_clipboard)

    def check_clipboard(self):
        if (self.clipboard.wait_is_text_available()):
            uri = self.clipboard.wait_for_text()
            if (self.last_text != uri):
                f = gio.File(uri = uri)
                if (f.get_uri_scheme() is not None):
                    print 'got new uri: ' + uri
                    for item in self.items:
                        item.remove_from_connection()
                    self.items = [ ClipboardMediaItem(self, uri, 0) ]
                    self.Updated()
                self.last_text = uri
        return True
        ## TODO: check for image data
    
    @property
    def parent(self):
        return self

    def get_children(self):
        return self.items, []


class ClipboardMediaItem(MediaItemMixin):
    def __init__(self, parent, uri, index):
        self.path = '%s/%s' % (parent.path, index)
        super(ClipboardMediaItem, self).__init__(parent.bus,
                                                 object_path=self.path)
        self.bus = parent.bus
        self.urls = [ uri ]
        self.parent = parent

        ## TODO: we probably want to figure these out from the stream, once
        ## we find a good streaming metadata library
        self.type = 'video.movie'
        self.display_name = 'Item %s' % index
        
    def get_details(self):
        ## TODO: need a streaming metadata library for more details
        url = self.urls[0]
        file_ext = os.path.splitext(url)[1].lower()
        if (file_ext in MIME_TYPES):
            mime_type = MIME_TYPES[file_ext]
        else:
            info = urllib.urlopen(url).info()
            content_type = info['Content-Type']
            if (content_type in MIME_TYPES.values()):
                mime_type = content_type
            else:
                mime_type = MIME_TYPES['avi']
        return {
            'MIMEType': mime_type
            }

