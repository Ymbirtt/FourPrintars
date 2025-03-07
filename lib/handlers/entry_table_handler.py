import logging


class EntryTableHandler:
    def __init__(self, entries):
        self._log = logging.getLogger("FourPrintars.entry_table_handler")
        self.entries = entries

    def on_match_selected(self, widget, model, iter_):
        selected_row = model[iter_]
        self._log.debug(f"Autolookup hit: Matched row {selected_row}")

        for entry in self.entries:
            value = selected_row[entry.data_column_idx]
            self._log.debug(f"Autolookup setting {entry.data_column_name} to {repr(value)}")
            entry.set_text(value)
