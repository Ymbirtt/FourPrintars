import csv

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class OutputField:
    def __init__(self, path, display_type):
        self.path = path
        self.display_type = display_type


class Table:
    def __init__(self, name, source, headers, data):
        self.name = name
        self.source = source
        self.output_fields = []
        self.headers = headers
        self.data = data
        self.header_map = {header: ii for ii, header in enumerate(headers)}

    @classmethod
    def from_csv(cls, name, csv_path):
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)
            data = Gtk.ListStore(*([str] * len(headers)))
            for row in reader:
                data.append(row)
        return cls(name, csv_path, headers, data)

    @classmethod
    def from_nothing(cls, name):
        return cls(name, '', [], [])

    def add_output_field(self, path, display_type):
        if all(of.path != path for of in self.output_fields):
            self.output_fields.append(OutputField(path, display_type))
