import csv
import sys
import copy
from lxml import etree
from pprint import pformat
from collections import defaultdict

import inkex
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from lib.handlers.main_handler import MainHandler
from lib.handlers.entry_table_handler import EntryTableHandler

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
            data = Gtk.ListStore(*([str]*len(headers)))
            for row in reader:
                data.append(row)
        return cls(name, csv_path, headers, data)

    @classmethod
    def from_nothing(cls, name):
        return cls(name, '', [], [])

    def add_output_field(self, path, display_type):
        if all(of.path != path for of in self.output_fields):
            self.output_fields.append(OutputField(path, display_type))

class FourPrintars(inkex.GenerateExtension):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.tables = {}
        self.template_path = None
        self.data_entries = {
            'fixed': {},
            'generated': defaultdict(dict),
        }
        self.outputs = {}
        self.records = None
        self.record_index_map = {}

        self.init_gtk()

    def init_gtk(self):
        handler = MainHandler(self)
        self.builder = Gtk.Builder()
        self.builder.add_from_file("ui/four_printars_main.glade")
        self.builder.connect_signals(handler)

        self.add_entry_window = self.builder.get_object("add_entry")
        self.inventory_window = self.builder.get_object("inventory")

        self.add_entry_window.set_transient_for(self.inventory_window)

        self.inventory_window.connect("destroy", Gtk.main_quit)

        self.data_entries['fixed']['rows'] = self.builder.get_object('inventory_rows')
        self.data_entries['fixed']['columns'] = self.builder.get_object('inventory_columns')
        self.data_entries['fixed']['bleed'] = self.builder.get_object('inventory_bleed')
        self.data_entries['fixed']['quantity'] = self.builder.get_object('add_entry_quantity')

    def render(self):
        flattened_records = []
        for record in self.records:
            record = tuple(record)
            record_as_dict = {field_name: record[field_idx] for field_name,
                    field_idx in self.record_index_map.items()}

            quantity = record_as_dict.pop('Quantity')
            flattened_records += [record_as_dict] * int(quantity)

        rows = int(self.data_entries['fixed']['rows'].get_text())
        columns = int(self.data_entries['fixed']['columns'].get_text())
        bleed = float(self.data_entries['fixed']['bleed'].get_text())

        renders_per_page = rows * columns
        num_pages = (len(flattened_records) + (len(flattened_records) % renders_per_page)) // renders_per_page
        last_page = self.svg.namedview.get_pages()[-1]

        last_page_x = last_page.x
        x = last_page.x + last_page.width + 10

        new_pages = []
        for ii in range(num_pages):
            new_page = self.svg.namedview.new_page(x=str(x), y=str(last_page.y),
                    width=str(last_page.width), height=str(last_page.height),
                    label=f"Templated page {ii}")
            new_pages.append(new_page)
            x += last_page.width + 10

        # print(pformat(flattened_records), file=sys.stderr)

        rendered_templates = [self.render_one_template(ii, record) for ii, record in enumerate(flattened_records)]

        for page, page_group in zip(new_pages, self.paginate(rendered_templates, rows, columns, bleed)):
            bbox = page_group.shape_box()
            x_offs = (page.width - bbox.width) / 2
            y_offs = (page.height - bbox.height) / 2
            transform = inkex.transforms.Transform()
            transform.add_translate(page.x + x_offs, page.y + y_offs)
            page_group.set("transform", transform)

            self.svg.add(page_group)

    def paginate(self, renders, rows, columns, bleed):
        renders_per_page = rows * columns

        for idx, start_pos in enumerate(range(0, len(renders), renders_per_page)):
            page_renders = renders[start_pos:start_pos + renders_per_page]

            x_coord = bleed
            y_coord = bleed
            x_idx = 0
            y_idx = 0
            max_row_height = 0

            page_group = inkex.Group.new(f"Template Page Group {idx}", id=f"template_page_group_{idx}")
            page_group.set("inkscape:groupmode", "layer")

            for render in page_renders:
                transform = inkex.transforms.Transform()
                transform.add_translate(x_coord, y_coord)
                render.set("transform", transform)
                page_group.append(render)

                bbox = self.template.getroot().get_page_bbox()
                x_coord += bbox.width + bleed
                if bbox.height > max_row_height:
                    max_row_height = bbox.height
                x_idx += 1
                if x_idx >= columns:
                    x_idx = 0
                    x_coord = bleed
                    y_idx += 1
                    y_coord += max_row_height + bleed
                    max_row_height = 0

            bbox = page_group.shape_box()
            bleed_box = inkex.elements.Rectangle.new(0, 0, bbox.width + bleed * 2, bbox.height + bleed * 2)
            bleed_box.style['fill'] = 'black'
            bleed_box.style['opacity'] = 1
            bleed_box.style['fill-opacity'] = 1
            page_group.insert(0, bleed_box)

            yield page_group

    def render_one_template(self, idx, record):
        new_g = inkex.Group.new(f"Template Instance {idx}", id=f"template_instance_{idx}")
        new_g.set("inkscape:groupmode", "layer")

        for child in self.template.findall('./*'):
            # print(child.tag, file=sys.stderr)
            # print(child.get('id'), file=sys.stderr)
            if "namedview" not in child.tag:
                new_g.append(copy.deepcopy(child))

        template_tags = new_g.findall(".//*[@data-fp-value]")
        for tag in template_tags:
            for child in list(tag):
                tag.remove(child)
            print(tag, file=sys.stderr)
            tag.text = record[tag.attrib['data-fp-value']]
            print(tag.text, file=sys.stderr)
            print("", file=sys.stderr)

        return new_g

    def select_template(self):
        dialog = Gtk.FileChooserDialog(
            title="Please choose an SVG template file",
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )

        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            Gtk.main_quit()

        self.template_path = dialog.get_filename()
        dialog.destroy()
        self.load_template()
        self.set_inventory_banner()

    def load_template(self):
        with open(self.template_path, 'r') as f:
            self.template = inkex.elements.load_svg(f)

        template_tags = self.template.findall("//*[@data-fp-value]")
        for tag in template_tags:
            table_name, model_path = tag.attrib['data-fp-value'].split('/', 1)
            print(f"Found template tag for {table_name}/{model_path}", file=sys.stderr)
            if table_name not in self.tables:
                if not table_name:
                    self.tables[table_name] = Table.from_nothing(table_name)
                else:
                    self.tables[table_name] = self.select_table(table_name)
                    self.set_inventory_banner()

            self.tables[table_name].add_output_field(model_path, tag.attrib['data-fp-type'])
            print(f"Output fields: {','.join(of.path for of in self.tables[table_name].output_fields)}", file=sys.stderr)

    def init_add_entry_form(self):
        main_grid = self.builder.get_object('add_entry_main_grid')

        for ii, table_name in enumerate(self.tables):
            print(f"Adding entry form for table named: {table_name}", file=sys.stderr)
            if not table_name:
                label = "Freeform fields"
            else:
                label = table_name
            new_frame = Gtk.Frame(label=table_name)
            main_grid.attach(new_frame, 0, ii+1, 1, 1)
            frame_grid = Gtk.Grid()
            new_frame.add(frame_grid)
            self.populate_frame_grid_for_table(frame_grid, self.tables[table_name])

        main_grid.show_all()

    def populate_frame_grid_for_table(self, frame_grid, table):
        entries = []
        output_fields = table.output_fields
        if table.header_map:
            print(table.header_map, file=sys.stderr)
            output_fields.sort(key=lambda x: table.header_map[x.path])

        for jj, output_field in enumerate(output_fields):
            print(f"Adding field for {output_field.path}", file=sys.stderr)

            new_label = Gtk.Label(label=output_field.path + ": ")
            frame_grid.attach(new_label, 2*jj, 0, 1, 1)

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

            self.data_entries['generated'][table.name][output_field.path] = entry
            frame_grid.attach(entry, 2*jj + 1, 0, 1, 1)
            entries.append(entry)

        handler = EntryTableHandler(entries)
        for entry in entries:
            if entry.get_completion():
                entry.get_completion().connect('match-selected', handler.on_match_selected)

    def add_record_to_inventory(self):
        record = {}
        record['Quantity'] = self.data_entries['fixed']['quantity'].get_text()
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

        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            print("Exit clicked...")
            Gtk.main_quit()

        ret = Table.from_csv(table_name, dialog.get_filename())
        dialog.destroy()
        return ret

    def run_workflow(self):
        self.set_inventory_banner()
        self.inventory_window.show_all()
        self.select_template()
        self.init_add_entry_form()
        self.init_record_table()
        Gtk.main()

    def init_record_table(self):
        num_fields = sum(len(table.output_fields) for table in self.tables.values())
        self.records = Gtk.ListStore(str, *[str] * num_fields)
        self.record_index_map = {"Quantity": 0}

        # treeview = Gtk.TreeView()
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
                inventory_view_column.set_fixed_width(100)
                inventory_view.append_column(inventory_view_column)
                inventory_view_column.pack_start(cellrenderertext, True)
                inventory_view_column.add_attribute(cellrenderertext, "text", ii)
                ii += 1

    def set_inventory_banner(self):
        inventory_banner = self.builder.get_object("inventory_banner")
        banner_text = ""

        if not self.template_path:
            banner_text += "Template file not yet loaded\n"
        else:
            banner_text += f"Loaded template: {self.template_path}\n"

        for name, table in self.tables.items():
            if table and name:
                banner_text += f"Loaded {name} table from: {table.source}\n"
            elif name:
                banner_text += f"{name} table not yet loaded...\n"

        banner_text.strip()
        inventory_banner.set_text(banner_text)

    def effect(self):
        self.run_workflow()

if __name__ == '__main__':
    FourPrintars().run()