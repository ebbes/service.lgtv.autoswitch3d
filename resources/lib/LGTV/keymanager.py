class DummyKeyManager(object):
    def load_client_key(self, host):
        # type: (str) -> str
        return None

    def save_client_key(self, host, key):
        # type: (str, str) -> ()
        pass

class SimpleKeyManager(object):
    def __init__(self, file_name):
        self.keyfile = file_name

    def load_client_key(self, host):
        # type: (str) -> str
        try:
            f = open(self.keyfile, 'r')
            key = f.read()
            f.close()
            return key
        except:
            return None

    def save_client_key(self, host, key):
        # type: (str, str) -> ()
        f = open(self.keyfile, 'w')
        f.write(key)
        f.close()
