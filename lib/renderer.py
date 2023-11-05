import sys
import inkex
import copy
import logging

class Renderer():
    def __init__(self, template, svg, options):
        self._template = template
        self._svg = svg
        self._options = {}
        self._parse_options(options)
        self._log = logging.getLogger(f"FourPrintars")

    def _parse_options(self, options):
        errors = []

        if set(options.keys()) != set(['rows', 'columns', 'bleed']):
            raise ValueError("Options don't make sense")

        try:
            self._options['rows'] = int(options['rows'])
        except ValueError:
            raise

        try:
            self._options['columns'] = int(options['columns'])
        except ValueError:
            raise

        try:
            self._options['bleed'] = float(options['bleed'])
        except ValueError:
            raise

    def render(self, records):
        renders_per_page = self._options['rows'] * self._options['columns']
        num_pages = (len(records) + (len(records) % renders_per_page)) // renders_per_page
        last_page = self._svg.namedview.get_pages()[-1]

        last_page_x = last_page.x
        x = last_page.x + last_page.width + 10

        new_pages = []
        for ii in range(num_pages):
            new_page = self._svg.namedview.new_page(x=str(x), y=str(last_page.y),
                    width=str(last_page.width), height=str(last_page.height),
                    label=f"Templated page {ii}")
            new_pages.append(new_page)
            x += last_page.width + 10

        rendered_templates = [self.render_one_template(ii, record)
                for ii, record in enumerate(records)]

        page_iter = self.paginate(
                        rendered_templates,
                        self._options['rows'],
                        self._options['columns'],
                        self._options['bleed'],
                    )

        for page, page_group in zip(new_pages, page_iter):
            bbox = page_group.shape_box()
            x_offs = (page.width - bbox.width) / 2
            y_offs = (page.height - bbox.height) / 2
            transform = inkex.transforms.Transform()
            transform.add_translate(page.x + x_offs, page.y + y_offs)
            page_group.set("transform", transform)

            self._svg.add(page_group)

        self._log.info(f"Successfully rendered {len(records)} records on {num_pages} pages")

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

        for child in self._template.findall('./*'):
            # print(child.tag, file=sys.stderr)
            # print(child.get('id'), file=sys.stderr)
            if "namedview" not in child.tag:
                new_g.append(copy.deepcopy(child))

        template_tags = new_g.findall(".//*[@data-fp-value]")
        for tag in template_tags:
            for child in list(tag):
                tag.remove(child)
            self._log.debug(tag)
            tag.text = record[tag.attrib['data-fp-value']]
            self._log.debug(tag.text)
            self._log.debug("")

        return new_g
