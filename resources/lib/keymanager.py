import xbmcaddon
__addon__ = xbmcaddon.Addon()

class KodiKeyManager(object):
    def load_client_key(self, host):
        # type: (str) -> str
        return __addon__.getSetting('lg_pairing_key')

    def save_client_key(self, host, key):
        # type: (str, str) -> ()
        if key != __addon__.getSetting('lg_pairing_key'):
            __addon__.setSetting('lg_pairing_key', key)
