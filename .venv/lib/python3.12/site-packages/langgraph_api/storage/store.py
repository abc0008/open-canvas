import os

from langgraph.checkpoint.memory import PersistentDict
from langgraph.store.memory import InMemoryStore


class DiskBackedInMemStore(InMemoryStore):
    def __init__(self, *args, filename=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.filename = filename
        self._data = PersistentDict(dict, filename=self.filename)
        try:
            self._data.load()
        except FileNotFoundError:
            pass

    def close(self):
        self._data.close()


_STORE_FILE = os.path.join(".langgraph_api", "store.pckl")
if not os.path.exists(".langgraph_api"):
    os.mkdir(".langgraph_api")
STORE = DiskBackedInMemStore(filename=_STORE_FILE)


def Store(*args, **kwargs):
    return STORE
