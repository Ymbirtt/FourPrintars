from lib.handlers.main_handler import MainHandler
from lib.handlers.entry_table_handler import EntryTableHandler
from lib.renderer import Renderer, RendererError
from lib.table import Table
from lib.list_store_log_handler import ListStoreLogHandler

import os
import os.path
import yaml
import logging
import traceback
import sys
from collections import defaultdict

import inkex
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class FourPrintars(inkex.GenerateExtension):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._log = logging.getLogger("FourPrintars")
        self._log.setLevel(logging.DEBUG)
        logging.basicConfig(stream=sys.stderr)
        self._log.debug("Debug logging enabled!")

        self.tables = {}
        self.template_path = None
        self.data_entries = {
            'fixed': {},
            'generated': defaultdict(dict),
        }
        self.outputs = {}
        self.records = None
        self.record_index_map = {}
        self.config_filepath = os.path.join(os.environ['HOME'], '.config', 'FourPrintars.yaml')

        self.init_gtk()

        self.config = self.load_config()
        self.save_config()

    def show_msg(self, text, message_type=Gtk.MessageType.INFO):
        dialog = Gtk.MessageDialog(
                    message_type=message_type,
                    text=text,
                    buttons=Gtk.ButtonsType.OK,
                 )
        dialog.run()
        dialog.destroy()

    def load_config(self):
        config_dir = os.path.dirname(self.config_filepath)

        if not os.path.exists(config_dir):
            os.mkdir(config_dir)
            if os.name == 'nt':
                import ctypes
                FILE_ATTRIBUTE_HIDDEN = 0x02

                ctypes.windll.kernel32.SetFileAttributesW(
                        config_dir.encode('utf-16le'), FILE_ATTRIBUTE_HIDDEN)

        if not os.path.exists(self.config_filepath):
            self.show_msg(f"This appears to be your first time running FourPrintars.\n\nYour config file lives at {self.config_filepath} - I've initialised an empty one for you.")
            self._log.info(f"Created new config at {self.config_filepath}")
            return {}
        else:
            with open(self.config_filepath, 'r') as f:
                config = yaml.load(f)
            self._log.info(f"Loaded config from {self.config_filepath}")
            return config

    def save_config(self):
        with open(self.config_filepath, 'w') as f:
            yaml.dump(self.config, f)

    def init_gtk(self):
        handler = MainHandler(self)
        self.builder = Gtk.Builder()
        self.builder.add_from_file("ui/four_printars_main.glade")
        self.builder.connect_signals(handler)

        self.inventory_window = self.builder.get_object("inventory")
        self.inventory_window.connect("destroy", Gtk.main_quit)

        self.data_entries['fixed']['rows'] = self.builder.get_object('inventory_rows')
        self.data_entries['fixed']['columns'] = self.builder.get_object('inventory_columns')
        self.data_entries['fixed']['bleed'] = self.builder.get_object('inventory_bleed')
        self.data_entries['fixed']['quantity'] = self.builder.get_object('add_entry_quantity')

        log_store = self.builder.get_object('status_entry_store')
        scrolling_window = self.builder.get_object('inventory_status_window')

        def autoscroll(self, widget, *args):
            adj = scrolling_window.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())

        self.builder.get_object('inventory_status').connect('size-allocate', autoscroll)
        self._log.addHandler(ListStoreLogHandler(log_store))

    def save_render_options(self, render_options):
        template_filename = os.path.basename(self.template_path)
        for key, value in render_options.items():
            self.update_config('default_render_option', template_filename, key, value)

    def load_render_options(self):
        template_filename = os.path.basename(self.template_path)
        if rows := self.get_config('default_render_option', template_filename, 'rows'):
            self.data_entries['fixed']['rows'].set_text(rows)

        if columns := self.get_config('default_render_option', template_filename, 'columns'):
            self.data_entries['fixed']['columns'].set_text(columns)

        if bleed := self.get_config('default_render_option', template_filename, 'bleed'):
            self.data_entries['fixed']['bleed'].set_text(bleed)

    def render(self):
        render_options = {
            'rows': self.data_entries['fixed']['rows'].get_text(),
            'columns': self.data_entries['fixed']['columns'].get_text(),
            'bleed': self.data_entries['fixed']['bleed'].get_text(),
        }
        try:
            renderer = Renderer(self.template, self.svg, render_options)
            self.save_render_options(render_options)

            flattened_records = []
            for record in self.records:
                record = tuple(record)
                record_as_dict = {field_name: record[field_idx] for field_name,
                        field_idx in self.record_index_map.items()}

                quantity = record_as_dict.pop('Quantity')
                flattened_records += [record_as_dict] * int(quantity)

            renderer.render(flattened_records)
            self.show_msg("Rendering finished!\n\nYou won't be able to see the results until you close Four Printars")

        except RendererError as e:
            msg = "Failed to render. Here's why:\n" + "\n".join(e.errors)
            self.show_msg(msg, message_type=Gtk.MessageType.ERROR)
        except Exception:
            msg = "Something went terribly wrong!\n" + traceback.format_exc()
            self.show_msg(msg, message_type=Gtk.MessageType.ERROR)

    def select_template(self):
        dialog = Gtk.FileChooserDialog(
            title="Please choose an SVG template file",
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )

        if default_template_dir := self.get_config('default_template_dir'):
            dialog.set_current_folder(default_template_dir)

        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            Gtk.main_quit()

        self.template_path = dialog.get_filename()
        self.update_config('default_template_dir', os.path.dirname(self.template_path))
        dialog.destroy()
        self.load_template()
        self.load_render_options()

    def get_config(self, *args):
        if len(args) < 1:
            raise RuntimeError("Attempted to get config without a valid path!")
        prefix_keys = args[:-1]
        final_key = args[-1]

        curr_config_dict = self.config
        for key in prefix_keys:
            if key not in curr_config_dict:
                curr_config_dict = {}
                break
            else:
                curr_config_dict = curr_config_dict[key]

        return curr_config_dict.get(final_key)

    def update_config(self, *args):
        if len(args) < 2:
            raise RuntimeError("Attempted to update config without a valid path!")
        prefix_keys = args[:-2]
        final_key = args[-2]
        value = args[-1]

        curr_config_dict = self.config
        for key in prefix_keys:
            if key not in curr_config_dict:
                curr_config_dict[key] = {}
            curr_config_dict = curr_config_dict[key]

        if curr_config_dict.get(final_key) != value:
            curr_config_dict[final_key] = value
            self.save_config()

    def load_template(self):
        with open(self.template_path, 'r') as f:
            self.template = inkex.elements.load_svg(f)

        template_tags = self.template.findall("//*[@data-fp-value]")
        for tag in template_tags:
            table_name, model_path = tag.attrib['data-fp-value'].split('/', 1)
            self._log.debug(f"Found template tag for {table_name}/{model_path}")
            if table_name not in self.tables:
                if not table_name:
                    self.tables[table_name] = Table.from_nothing(table_name)
                else:
                    self.tables[table_name] = self.select_table(table_name)

            self.tables[table_name].add_output_field(model_path, tag.attrib['data-fp-type'])

        self._log.debug(f"Output fields: {','.join(of.path for of in self.tables[table_name].output_fields)}")
        self._log.info(f"Loaded template: {self.template_path}")

    def init_add_entry_form(self):
        main_grid = self.builder.get_object('add_entry_main_grid')

        for ii, table_name in enumerate(self.tables):
            self._log.debug(f"Adding entry form for table named: {table_name}")
            new_frame = Gtk.Frame(label=table_name)
            main_grid.attach(new_frame, 0, ii + 1, 1, 1)
            frame_grid = Gtk.Grid()
            new_frame.add(frame_grid)
            self.populate_frame_grid_for_table(frame_grid, self.tables[table_name])

        main_grid.show_all()

    def populate_frame_grid_for_table(self, frame_grid, table):
        entries = []
        output_fields = table.output_fields
        if table.header_map:
            self._log.debug("Table header map:" + str(table.header_map))
            output_fields.sort(key=lambda x: table.header_map[x.path])

        output_field_idx = 0
        for output_field in output_fields:
            self._log.debug(f"Adding field for {output_field.path}")

            if output_field.display_type == "key":
                entry = Gtk.SearchEntry()
                entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, 'system-search-symbolic')
                completion = Gtk.EntryCompletion()
                completion.set_model(table.data)
                completion.set_text_column(table.header_map[output_field.path])
                completion.set_inline_completion(True)
                entry.set_completion(completion)
            elif output_field.display_type == "displayonly":
                entry = Gtk.Entry()
                entry.set_editable(False)
            elif output_field.display_type == "editable":
                entry = Gtk.Entry()
            elif output_field.display_type == "hidden":
                entry = Gtk.Entry()
                entry.set_editable(False)
                entry.set_visible(False)

            entry.data_column_name = output_field.path
            if table.header_map:
                entry.data_column_idx = table.header_map[output_field.path]

            self.data_entries['generated'][table.name][output_field.path] = entry
            if output_field.display_type != 'hidden':
                new_label = Gtk.Label(label=output_field.path)
                frame_grid.attach(new_label, 2 * output_field_idx, 0, 1, 1)

                frame_grid.attach(entry, 2 * output_field_idx + 1, 0, 1, 1)

                output_field_idx += 1

            entries.append(entry)

        handler = EntryTableHandler(entries)
        for entry in entries:
            if entry.get_completion():
                if not table.header_map:
                    raise Exception("A key field has been used on a non-table-backed storage. I can't look up things from something that's not a table!")
                entry.get_completion().connect('match-selected', handler.on_match_selected)

    def add_record_to_inventory(self):
        qty_text = self.data_entries['fixed']['quantity'].get_text()
        try:
            q = int(qty_text)
            if q <= 0:
                raise ValueError(qty_text)
        except ValueError:
            self.show_msg(f"Could not parse \"{qty_text}\" as a quantity. Please input a whole number", message_type=Gtk.MessageType.ERROR)
            return

        record = {}

        record['Quantity'] = qty_text
        for table_name, output_dict in self.data_entries['generated'].items():
            for output_field_name, entry in output_dict.items():
                record[table_name + '/' + output_field_name] = self.data_entries['generated'][table_name][output_field_name].get_text()

        list_store_record = [None for _ in self.record_index_map]
        for field_name, field_idx in self.record_index_map.items():
            list_store_record[field_idx] = record[field_name]

        self.records.append(list_store_record)

    def remove_current_record(self):
        inventory_view = self.builder.get_object("inventory_view")
        row_path, column = inventory_view.get_cursor()

        iter_ = self.records.get_iter(row_path)
        if iter_:
            self.records.remove(iter_)

    def select_table(self, table_name):
        dialog = Gtk.FileChooserDialog(
            title=f"Please choose a CSV file to load the {table_name} table",
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )
        dialog.set_position(Gtk.WindowPosition.CENTER_ALWAYS)

        if default_table_file := self.get_config('default_table_file', table_name):
            dialog.set_filename(default_table_file)

        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            Gtk.main_quit()

        filename = dialog.get_filename()
        ret = Table.from_csv(table_name, filename)
        self.update_config('default_table_file', table_name, filename)

        dialog.destroy()

        self._log.info(f"Loaded {table_name} table from: {filename}")
        return ret

    def run_workflow(self):
        self.inventory_window.show_all()
        self.select_template()
        self.init_add_entry_form()
        self.init_record_table()
        Gtk.main()

    def init_record_table(self):
        num_fields = sum(len(table.output_fields) for table in self.tables.values())
        self.records = Gtk.ListStore(str, *[str] * num_fields)
        self.record_index_map = {"Quantity": 0}

        inventory_view = self.builder.get_object('inventory_view')
        inventory_view.set_model(self.records)

        cellrenderertext = Gtk.CellRendererText()
        inventory_view_column = Gtk.TreeViewColumn("Quantity")
        inventory_view.append_column(inventory_view_column)
        inventory_view_column.pack_start(cellrenderertext, True)
        inventory_view_column.add_attribute(cellrenderertext, "text", 0)

        ii = 1
        for table_name, table in self.tables.items():
            for output_field in table.output_fields:
                full_path = table_name + '/' + output_field.path
                self.record_index_map[full_path] = ii

                cellrenderertext = Gtk.CellRendererText()
                inventory_view_column = Gtk.TreeViewColumn(full_path)
                inventory_view_column.set_resizable(True)
                inventory_view_column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
                if output_field.display_type == 'hidden':
                    inventory_view_column.set_fixed_width(0)
                else:
                    inventory_view_column.set_fixed_width(100)
                inventory_view.append_column(inventory_view_column)
                inventory_view_column.pack_start(cellrenderertext, True)
                inventory_view_column.add_attribute(cellrenderertext, "text", ii)
                ii += 1

    def effect(self):
        self.run_workflow()


if __name__ == '__main__':
    FourPrintars().run()
