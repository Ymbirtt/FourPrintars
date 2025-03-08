import inkex
import copy
import logging


class RendererError(Exception):
    def __init__(self, *args, **kwargs):
        self.errors = kwargs.pop('errors')
        super().__init__(*args, **kwargs)


class Renderer():
    def __init__(self, template, svg, options):
        self._template = template
        template_root = template.getroot()
        width = template_root.get('width')
        height = template_root.get('height')
        self._template_width_mm = inkex.units.convert_unit(width, 'mm')
        self._template_height_mm = inkex.units.convert_unit(height, 'mm')
        self._svg = svg
        self._options = {}
        self._parse_options(options)
        self._log = logging.getLogger("FourPrintars")

    def _parse_options(self, options):
        errors = []

        if set(options.keys()) != set(['rows', 'columns', 'bleed']):
            raise ValueError("Options don't make sense")

        try:
            self._options['rows'] = int(options['rows'])
            if self._options['rows'] <= 0:
                raise ValueError(self._options['rows'])
        except ValueError:
            errors.append(f"Could not parse \"{options['rows']}\" as a number of rows. Please input a whole number")

        try:
            self._options['columns'] = int(options['columns'])
            if self._options['columns'] <= 0:
                raise ValueError(self._options['columns'])
        except ValueError:
            errors.append(f"Could not parse \"{options['columns']}\" as a number of columns. Please input a whole number")

        try:
            self._options['bleed'] = float(options['bleed'])
            if self._options['bleed'] < 0:
                raise ValueError(self._options['bleed'])
        except ValueError:
            errors.append(f"Could not parse \"{options['bleed']}\" as a bleed width. Please input a number (decimals are allowed)")

        if errors:
            raise RendererError("Invalid options", errors=errors)

    def render(self, records):
        renders_per_page = self._options['rows'] * self._options['columns']
        num_records_in = len(records)
        num_pages = (len(records) + (len(records) % renders_per_page)) // renders_per_page
        num_blanks = 0

        if len(records) % renders_per_page != 0:
            # If the number of records isn't an integer multiple of the number
            # of records per page, create some blank ones to round up
            num_blanks = (renders_per_page - len(records) % renders_per_page)
            records += [{k: "" for k in records[0].keys()}] * num_blanks
            num_pages += 1

        self._log.debug(f"Rendering {num_records_in} plus {num_blanks} blanks in a {self._options['columns']}x{self._options['rows']} grid on {num_pages} pages")

        last_page = self._svg.namedview.get_pages()[-1]
        space_between_pages = 10

        x = last_page.x + last_page.width + space_between_pages

        new_pages = []
        for ii in range(num_pages):
            new_page = self._svg.namedview.new_page(x=str(x), y=str(last_page.y),
                    width=str(last_page.width), height=str(last_page.height),
                    label=f"Templated page {ii}")
            new_pages.append(new_page)
            x += last_page.width + space_between_pages

        rendered_templates = [self.render_one_template(ii, record)
                for ii, record in enumerate(records)]

        rows = self._options['rows']
        columns = self._options['columns']
        bleed = self._options['bleed']
        bleed_box_width = (self._template_width_mm + bleed) * columns + bleed
        bleed_box_height = (self._template_height_mm + bleed) * rows + bleed
        page_iter = self.paginate(
                        rendered_templates,
                        rows,
                        columns,
                        bleed,
                        bleed_box_width,
                        bleed_box_height,
                    )

        for page, page_group in zip(new_pages, page_iter):
            x_offs = (page.width - bleed_box_width) / 2
            y_offs = (page.height - bleed_box_height) / 2
            transform = inkex.transforms.Transform()
            transform.add_translate(page.x + x_offs, page.y + y_offs)
            page_group.set("transform", transform)

        self._log.info(f"Successfully rendered {num_records_in} records on {num_pages} pages")

    def paginate(self, renders, rows, columns, bleed, bleed_box_width,
            bleed_box_height):
        renders_per_page = rows * columns

        for idx, start_pos in enumerate(range(0, len(renders), renders_per_page)):
            page_renders = renders[start_pos:start_pos + renders_per_page]

            x_coord = bleed
            y_coord = bleed
            x_idx = 0
            y_idx = 0
            max_row_height = 0

            page_group = inkex.Group.new(f"Template Page Group {idx}", id=f"template_page_group_{idx}")
            self._svg.add(page_group)
            # page_group.set("inkscape:groupmode", "layer")

            for render in page_renders:
                transform = inkex.transforms.Transform()
                transform.add_translate(x_coord, y_coord)
                render.set("transform", transform)
                page_group.append(render)

                bbox = self._template.getroot().get_page_bbox()
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

            bleed_box = inkex.elements.Rectangle.new(0, 0, bleed_box_width, bleed_box_height)
            bleed_box.style['fill'] = 'black'
            bleed_box.style['opacity'] = 1
            bleed_box.style['fill-opacity'] = 1
            page_group.insert(0, bleed_box)

            yield page_group

    def render_one_template(self, idx, record):
        new_g = inkex.Group.new(f"Template Instance {idx}", id=f"template_instance_{idx}")
        # new_g.set("inkscape:groupmode", "layer")

        self._log.debug(f"Render {idx}: {record}")

        for child in self._template.findall('./*'):
            # print(child.tag, file=sys.stderr)
            # print(child.get('id'), file=sys.stderr)
            if "namedview" not in child.tag:
                new_g.append(copy.deepcopy(child))

        template_tags = new_g.findall(".//*[@data-fp-value]")
        for tag in template_tags:
            for child in list(tag):
                tag.remove(child)
            tag.text = record[tag.attrib['data-fp-value']]

        return new_g
