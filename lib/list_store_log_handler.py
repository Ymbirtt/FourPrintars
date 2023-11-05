import logging

class ListStoreLogHandler(logging.Handler):
    def __init__(self, list_store, *args):
        super().__init__(*args)
        self.__list_store = list_store

    def emit(self, record):
        msg = self.format(record)
        self.__list_store.append([msg])
