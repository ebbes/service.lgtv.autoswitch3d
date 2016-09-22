import xbmc, xbmcaddon
import os
import sys
from resources.lib import tools

from resources.lib.LGTV.lgtv import LGTV

__addon__ = xbmcaddon.Addon()
__addonname__ = __addon__.getAddonInfo('name')
__addonID__ = __addon__.getAddonInfo('id')
__path__ = __addon__.getAddonInfo('path')
__version__ = __addon__.getAddonInfo('version')
__LS__ = __addon__.getLocalizedString

__IconConnected__ = xbmc.translatePath(os.path.join( __path__,'resources', 'media', 'ok.png'))
__IconError__ = xbmc.translatePath(os.path.join( __path__,'resources', 'media', 'fail.png'))
__IconDefault__ = xbmc.translatePath(os.path.join( __path__,'resources', 'media', 'default.png'))

def main():
    tools.notifyLog("Scanning for LG Smart TV Devices running WebOS...", level=xbmc.LOGDEBUG)

    ip = LGTV(log=tools.simpleLog).discover_ip(tries=5)

    if ip is None:
        tools.notifyLog("No LG Smart TV found.")
        tools.dialogOSD(__LS__(30050))
        return

    __addon__.setSetting('lg_host', ip)
    tools.notifyLog('Found LG Smart TV at %s' % ip)
    tools.dialogOSD(__LS__(30051) % ip)

if __name__ == '__main__':
    main()
