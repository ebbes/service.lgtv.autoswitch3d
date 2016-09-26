import xbmc, xbmcaddon
import os
import json
import re
from resources.lib import tools
from resources.lib.keymanager import KodiKeyManager

from resources.lib.LGTV.lgtv import LGTV
from resources.lib.LGTV.enums import Display3dMode

# when checking for current 3D mode via getStereoscopicMode,
# wait for WAIT_FOR_MODE_SELECT seconds. If a 3D mode change
# has happened within this interval, return True, else return
# False. This accounts for the user manually selecting the 3D
# mode when starting a video.
WAIT_FOR_MODE_SELECT = 60

# interval to send pong (keepalive) requests
# (keep under 5 minutes to prevent connection drops by TV)
PONG_INTERVAL = 60

__addon__ = xbmcaddon.Addon()
__addonname__ = __addon__.getAddonInfo('name')
__addonID__ = __addon__.getAddonInfo('id')
__path__ = __addon__.getAddonInfo('path')
__version__ = __addon__.getAddonInfo('version')
__LS__ = __addon__.getLocalizedString

__IconConnected__ = xbmc.translatePath(os.path.join(__path__,'resources', 'media', 'ok.png'))
__IconError__ = xbmc.translatePath(os.path.join(__path__,'resources', 'media', 'fail.png'))
__IconDefault__ = xbmc.translatePath(os.path.join(__path__,'resources', 'media', 'default.png'))
__IconKodi__ = xbmc.translatePath(os.path.join(__path__, 'resources', 'media', 'kodi.png'))

class Service(xbmc.Player):
    def __init__(self):
        xbmc.Player.__init__(self)
        self.lgtv = LGTV(KodiKeyManager(), log=tools.simpleLog)

        self.isPlaying3D = None
        self.mode3D = Display3dMode.OFF

        self.readSettings()

    def readSettings(self):
        self.lg_host = __addon__.getSetting('lg_host')
        self.lg_host = None if self.lg_host == '' else self.lg_host
        self.lg_pairing_key = __addon__.getSetting('lg_pairing_key')
        self.enable_discovery = __addon__.getSetting('lg_enable_discovery')
        self.force_discovery = __addon__.getSetting('lg_force_discovery')

        host_was_empty = self.lg_host is None or self.force_discovery
        if host_was_empty and self.enable_discovery:
            self.discover()

        if self.lg_host is None:
            # no host found
            tools.notifyLog("No LG TV found on network and no TV is configured in settings")
            tools.notifyOSD(__addonname__, __LS__(30101), icon=__IconError__)
            self.monitor.abortRequested = True
            return

        try:
            success = self.lgtv.connect(self.lg_host, __addonname__)
            if not success:
                raise Exception("LGTV.connect() failed")
            tools.notifyLog("Connected to TV at %s" % self.lg_host)
            #tools.notifyOSD(__addonname__, __LS__(30102) % self.lg_host, icon=__IconConnected__)
            self.lgtv.toast(__LS__(30103), icon_file=__IconKodi__)
        except Exception as e:
            # try new discovery
            if not host_was_empty and self.enable_discovery:
                # we didn't discover before
                self.discover()

                # try this newly discovered host
                if self.lg_host is not None:
                    try:
                        success = self.lgtv.connect(self.lg_host, __addonname__)
                        if not success:
                            raise Exception("LGTV.connect() failed")
                        tools.notifyLog("Connected to TV at %s" % self.lg_host)
                        #tools.notifyOSD(__addonname__, __LS__(30102) % self.lg_host, icon=__IconConnected__)
                        self.lgtv.toast(__LS__(30103), icon_file=__IconKodi__)
                    except Exception as e:
                        tools.notifyLog("Could not connect to TV at %s: %s" % (self.lg_host, str(e)), level=xbmc.LOGERROR)
                        tools.notifyOSD(__addonname__, __LS__(30100) % self.lg_host, icon=__IconError__)
                        self.monitor.abortRequested = True
            else:
                # host found via recovery could not be connected to
                tools.notifyLog("Could not connect to TV at %s: %s" % (self.lg_host, str(e)), level=xbmc.LOGERROR)
                tools.notifyOSD(__addonname__, __LS__(30100) % self.lg_host, icon=__IconError__)
                self.monitor.abortRequested = True


    def discover(self):
        # try to discover host
        self.lg_host = self.lgtv.discover_ip(tries=5, timeout=3)
        __addon__.setSetting('lg_host', self.lg_host)


    def getStereoscopicMode(self):
        mode = {
            "off": Display3dMode.OFF,
            "split_vertical": Display3dMode.SIDE_SIDE_HALF,
            "split_horizontal": Display3dMode.TOP_BOTTOM,
            "row_interleaved": Display3dMode.LINE_INTERLEAVE_HALF,
            "hardware_based": Display3dMode.FRAME_SEQUENTIAL,       # TODO: correct?
            "anaglyph_cyan_red": Display3dMode.OFF,                 # works without 3D mode set
            "anaglyph_green_magenta": Display3dMode.OFF,            # works without 3D mode set
            "monoscopic": Display3dMode.OFF
        }
        query = {
                "jsonrpc": "2.0",
                "method": "GUI.GetProperties",
                "params": {"properties": ["stereoscopicmode"]},
                "id": 1
        }
        _poll = WAIT_FOR_MODE_SELECT
        while _poll > 0:
            try:
                res = json.loads(xbmc.executeJSONRPC(json.dumps(query, encoding='utf-8')))
                if 'result' in res and 'stereoscopicmode' in res['result']:
                    res = res['result']['stereoscopicmode'].get('mode')
                    if self.mode3D != mode[res]:
                        tools.notifyLog('Stereoscopic mode has changed to %s' % (mode[res]))
                        self.mode3D = mode[res]
                        return True
                    _poll -= 1
                    xbmc.sleep(1000)
                else:
                    break
            except SystemExit:
                tools.notifyLog('System will terminate this script, closing it.', level=xbmc.LOGERROR)
                break
            except Exception as e:
                tools.notifyLog("Could not determine stereoscopic mode: %s", e)

        tools.notifyLog('Could not determine steroscopic mode', level=xbmc.LOGERROR)
        return False

    def onPlayBackStarted(self):
        self.switch3D()

    def onPlayBackStopped(self):
        self.switch3D()

    def onPlayBackEnded(self):
        self.switch3D()

    def switch3D(self):
        if self.getStereoscopicMode():
            tools.notifyLog('switching to 3D mode %s' % self.mode3D, level=xbmc.LOGDEBUG)
            success, msg = self.lgtv.set_3D_Mode(self.mode3D)
            if success:
                return

            # in case something _seriously_ failed during previous communication, try clean reconnect
            if not self.lgtv.is_connected():
                tools.notifyLog("Not connected, attempting reconnect")
                success = self.lgtv.connect(self.lg_host, __addonname__)
                if not success:
                    tools.notifyLog("Reconnect failed")
                    tools.notifyOSD(__addonname__, __LS__(30100) % self.lg_host, icon=__IconError__)
                    return

                tools.notifyLog("Reconnected to TV at %s" % self.lg_host)
                #tools.notifyOSD(__addonname__, __LS__(30102) % self.lg_host, icon=__IconConnected__)
                self.lgtv.toast(__LS__(30104), icon_file=__IconKodi__)

            success, msg = self.lgtv.set_3D_Mode(self.mode3D)
            if not success:
                tools.notifyLog(msg)
                if not self.lgtv.toast(msg, icon_file=__IconKodi__):
                    tools.notifyOSD(__addonname__, msg, icon=__IconError__)

    def keepConnectionAlive(self):
        self.lgtv.send_pong()

if __name__ == '__main__':
    SwitcherService = Service()

    monitor = xbmc.Monitor()

    while not monitor.abortRequested():
        if monitor.waitForAbort(PONG_INTERVAL):
            break
        # send pong message (does not result in server response)
        # to keep connection alive (server will close idle connections
        # after 5 minutes)
        SwitcherService.keepConnectionAlive()

    del SwitcherService
    tools.notifyLog('Service finished')
