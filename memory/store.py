class MemoryStore:
    def __init__(self):
        # Internal dictionary. Every function will interact with this dictionary
        self._store = {}
        
    # Set: Inserts key, value pair
    def set(self, key, value):
        self._store[key] = value

    # Get: Retrieves key if it exists. Otherwise, does nothing
    def get(self, key, default=None):
        # Im using .get() and not [] because [] can lead to crash if missing
        return self._store.get(key, default)

    # Delete: Removes key if it exists. Otherwise, does nothing
    def delete(self, key):
        if key in self._store:
            del self._store[key]

    # Clear: Resets memory
    def clear(self):
        self._store.clear()