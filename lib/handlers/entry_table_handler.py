import time

class EntryTableHandler:
    def __init__(self, entries):
        self.entries = entries

    def on_match_selected(self, widget, model, iter_):
        selected_row = model[iter_]
        for entry, value in zip(self.entries, selected_row):
            entry.set_text(value)
