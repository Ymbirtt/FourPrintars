import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

class MainHandler:
    def __init__(self, app):
        self.app = app

    def cancel_click(self, *args):
        Gtk.main_quit()

    def add_record_click(self, *args):
        self.app.add_record_to_inventory()

    def remove_record_click(self, *args):
        self.app.remove_current_record()

    def render_click(self, *args):
        self.app.render()
