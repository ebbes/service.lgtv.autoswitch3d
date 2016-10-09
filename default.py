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
    THREE_D_MODE_MAPPING = {
        "off": Display3dMode.OFF,
        "split_vertical": Display3dMode.SIDE_SIDE_HALF,
        "split_horizontal": Display3dMode.TOP_BOTTOM,
        "row_interleaved": Display3dMode.LINE_INTERLEAVE_HALF,
        "hardware_based": Display3dMode.FRAME_SEQUENTIAL,       # TODO: correct?
        "anaglyph_cyan_red": Display3dMode.OFF,                 # works without 3D mode set
        "anaglyph_green_magenta": Display3dMode.OFF,            # works without 3D mode set
        "monoscopic": Display3dMode.OFF
    }
    JSONRPC_QUERY = {
            "jsonrpc": "2.0",
            "method": "GUI.GetProperties",
            "params": {"properties": ["stereoscopicmode"]},
            "id": 1
    }

    def __init__(self):
        xbmc.Player.__init__(self)
        self.monitor = xbmc.Monitor()
        self.abortRequested = False
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
        self.switch_on_pause = __addon__.getSetting('lg_switch_on_pause')
        self.switch_on_resume = __addon__.getSetting('lg_switch_on_resume')
        self.pause_while_switching = __addon__.getSetting('lg_pause_while_switching')

        host_was_empty = self.lg_host is None or self.force_discovery
        if host_was_empty and self.enable_discovery:
            self.discover()

        if self.lg_host is None:
            # no host found
            tools.notifyLog("No LG TV found on network and no TV is configured in settings")
            tools.notifyOSD(__addonname__, __LS__(30101), icon=__IconError__)
            self.abortRequested = True
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
                        self.abortRequested = True
            else:
                # host found via recovery could not be connected to
                tools.notifyLog("Could not connect to TV at %s: %s" % (self.lg_host, str(e)), level=xbmc.LOGERROR)
                tools.notifyOSD(__addonname__, __LS__(30100) % self.lg_host, icon=__IconError__)
                self.abortRequested = True


    def discover(self):
        # try to discover host
        self.lg_host = self.lgtv.discover_ip(tries=5, timeout=3)
        __addon__.setSetting('lg_host', self.lg_host)


    def getStereoscopicMode(self):
        for _ in range(WAIT_FOR_MODE_SELECT):
            try:
                res = json.loads(xbmc.executeJSONRPC(json.dumps(self.JSONRPC_QUERY, encoding='utf-8')))
                tools.notifyLog(str(res), level=xbmc.LOGNOTICE)
                tools.notifyLog("Stereo mode: " + xbmc.getInfoLabel("System.StereoscopicMode"), level=xbmc.LOGNOTICE)
                if 'result' in res and 'stereoscopicmode' in res['result']:
                    res = res['result']['stereoscopicmode'].get('mode')
                    mapped = self.THREE_D_MODE_MAPPING[res]
                    if self.mode3D != mapped:
                        self.mode3D = mapped
                        tools.notifyLog('Stereoscopic mode has changed to %s' % (Display3dMode.to_string(self.mode3D)))
                        return True
                    if self.monitor.waitForAbort(0.5):
                        raise SystemExit
                else:
                    tools.notifyLog('Could not determine stereoscopic mode: stereoscopicmode not in result or result missing in JSON RPC response')
                    return False
            except SystemExit:
                tools.notifyLog('System will terminate this script, closing it.', level=xbmc.LOGERROR)
                return False
            except Exception as e:
                tools.notifyLog("Could not determine stereoscopic mode: %s" % e, level=xbmc.LOGERROR)
                return False

        # no 3D mode change happened
        return False

    def onPlayBackStarted(self):
        self.switch3D(self.pause_while_switching)

    def onPlayBackStopped(self):
        self.switch3D(False)

    def onPlayBackEnded(self):
        self.switch3D(False)

    def onPlayBackPaused(self):
        # on Alt+Tab switching, TV might reset mode to 2Dto3D.
        # Simply re-set current 3D mode when paused/resumed to
        # have a quick way to re-set correct mode.
        if self.switch_on_pause:
            self.reswitch3D(False)

    def onPlayBackResumed(self):
        # on Alt+Tab switching, TV might reset mode to 2Dto3D.
        # Simply re-set current 3D mode when paused/resumed to
        # have a quick way to re-set correct mode.
        if self.switch_on_resume:
            self.reswitch3D(self.pause_while_switching)

    def switch3D(self, auto_pause):
        if self.getStereoscopicMode():
            tools.notifyLog('Switching to 3D mode %s' % Display3dMode.to_string(self.mode3D))
            if auto_pause:
                # pause playback during switching
                self.pause()
            try:
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
            finally:
                if auto_pause:
                    # resume playback after switching
                    self.pause()

    def reswitch3D(self, auto_pause):
        mode = self.lgtv.get_3D_Mode()

        if mode == Display3dMode.ERROR:
            tools.notifyLog("Could not get current 3D mode")
            if not self.lgtv.toast("Could not get current 3D mode", icon_file=__IconKodi__):
                tools.notifyOSD(__addonname__, "Could not get current 3D mode", icon=__IconError__)

        if mode == self.mode3D:
            return

        if auto_pause:
            # pause playback until 3D mode is switched
            self.pause()
        success, msg = self.lgtv.set_3D_Mode(self.mode3D)
        if not success:
            tools.notifyLog(msg)
            if not self.lgtv.toast(msg, icon_file=__IconKodi__):
                tools.notifyOSD(__addonname__, msg, icon=__IconError__)
        if auto_pause:
            # resume
            self.pause()


    def keepConnectionAlive(self):
        self.lgtv.send_pong()

if __name__ == '__main__':
    service = Service()

    while not service.monitor.abortRequested() and not service.abortRequested:
        if service.monitor.waitForAbort(PONG_INTERVAL):
            break
        # send pong message (does not result in server response)
        # to keep connection alive (server will close idle connections
        # after 5 minutes)
        service.keepConnectionAlive()

    if service.lgtv.is_connected():
        service.lgtv.disable_3D()

    del service
    tools.notifyLog('Service finished')
