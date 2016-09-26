# based on information from https://mym.hackpad.com/ep/pad/static/rLlshKkzdNj

################################################################################
# BUILTIN MODULES
################################################################################
from __future__ import print_function, unicode_literals
import json
import socket
import time
import uuid
import base64

################################################################################
# SHIPPED MODULES
################################################################################
# NOTE: upstream websocket always sets an Origin header.
# However, this must not be set or webOS will reject WebSocket requests
# with "invalid origin". Therefore, shipped websocket package
# has removed Origin headers (in _handshake.py).
from . import websocket  # LGPL

################################################################################
# HELPER MODULES
################################################################################
from .enums import *
from .keymanager import DummyKeyManager

################################################################################
# PYTHON 2/3 COMPATIBILITY
################################################################################
try:
    # Python 3 has a 2-argument bytes() function.
    bytes("will_fail_on_python_2", "utf8")

    def str2bytes(s):
        # we need bytes instead of str in Python 3 in some places
        return bytes(s, "utf8")

    # for instance checking in python 3
    basestring = (str, bytes)
    unicode = str
except:
    def str2bytes(s):
        # Python 2 does not distinguish between str and bytes
        return s

    # basestring and unicode are correctly defined

################################################################################
# ACTUAL CODE
################################################################################

class LGTV(object):
    def __init__(self, key_manager=DummyKeyManager(), log=print):
        # type: () -> None
        self.last_host = None           # type: str
        self.wsocket = None             # type: websocket.WebSocket
        self.pointer_socket = None      # type: websocket.WebSocket
        self.command_counter = 0        # type: int
        self.pairing_key = ""           # type: str
        self.random_prefix = ""         # type: str
        self.is_paired = False          # type: bool
        self.log = log                  # type: (...) -> ()
        self.key_manager = key_manager  # type: DummyKeyManager compatible class

    def is_connected(self):
        # type: () -> bool
        if self.wsocket is None:
            return False
        return self.wsocket.connected and self.is_paired

    def _is_pointer_connected(self):
        # type: () -> bool
        if self.pointer_socket is None:
            return False
        return self.pointer_socket.connected

    def discover_ip(self, tries=5, timeout=3):
        # type: (int) -> str

        if tries < 1:
            raise ValueError("tries has to be >= 1")

        if timeout < 2:
            # we will send a maximum SSDP wait time of (timeout - 1),
            # therefore 2 is minimum.
            self.log("Timeout too small, reset to 2 seconds")
            timeout = 2
        if timeout > 120:
            # too big according to UPnP
            self.log("Timeout too big, reset to 120 seconds")
            timeout = 120

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.bind(("", 0)) # bind to random free port

        address = None
        i = 0
        for i in range(tries):
            if address is not None:
                break
            self._send_ssdp_discover(sock, timeout - 1, i + 1)

            while True:
                # get every response to our search datagram
                try:
                    data, addr = sock.recvfrom(1024) # actual message size should be way below 1024 byte.
                    if str2bytes("WebOS") in data or str2bytes("LG Smart TV") in data:
                        address = addr
                        break
                except:
                    # probably timeout, break response-reading loop
                    break

        if address is None:
            self.log("Didn't find TV using SSDP")
            return None

        self.log("Found TV at", address[0])
        return address[0] # IP

    def _send_ssdp_discover(self, sock, response_timeout=2, try_no=None):
        # type: (socket._socketobject, int) -> ()
        # see http://developer.lgappstv.com/TV_HELP/index.jsp?topic=%2Flge.tvsdk.references.book%2Fhtml%2FUDAP%2FUDAP%2FM+SEARCH+Request.htm
        # for M-SEARCH request description

        host = "239.255.255.250"
        port = 1900

        # according to above document, 1 <= MX <= 4 should hold.
        # however, UPnP spec says
        # "MX: Maximum wait time in seconds. Should be between 1 and 120 inclusive. Device responses should be delayed a
        #      random duration between 0 and this many seconds to balance load for the control point when it processes responses.
        #      This value may be increased if a large number of devices are expected to respond."
        # (source: http://www.upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.0-20080424.pdf)
        # Therefore, we'll just choose 2 as default.

        message = (
            "M-SEARCH * HTTP/1.1\r\n" +
            "HOST: 239.255.255.250:1900\r\n" +
            'MAN: "ssdp:discover"\r\n' +
            "MX: " + str(response_timeout) + "\r\n" +
            "ST: urn:dial-multiscreen-org:service:dial:1\r\n" +
            "USER-AGENT: UDAP/2.0\r\n\r\n") # close with double \r\n
        # according to LG, USER-AGENT is required (everything except UDAP/2.0 can be omitted)
        # (although my TV responds even when USER-AGENT is missing completely...)

        if try_no is None:
            self.log("Sending SSDP search message")
        else:
            self.log("Sending SSDP search message, try", try_no)
        sock.sendto(str2bytes(message), (host, port))

    @staticmethod
    def _sanitize_host_string(host):
        # type: (str) -> str
        if not host.startswith("ws://"):
            host = "ws://" + host
        if host.endswith("/"):
            # remove trailing slash so we can check for port easily
            host = host[:-1]
        if not host.endswith(":3000"):
            host = host + ":3000"

        return host

    @staticmethod
    def _generate_pairing_request(msg_id, app_name, client_key=None):
        # type: (str) -> (str, str)

        pairing_request = {
            "type": "register",
            "id": msg_id,
            "payload": {
                "pairingType": "PROMPT",
                "manifest": {
                    "localizedAppNames": {
                        "": str(app_name)
                    },
                    #"localizedVendorNames": { # seems to be ignored by TV
                    #    "": "Whatever"
                    #},
                    "permissions": [ # seems to be everything possible (maybe too many permissions!)
                        'APP_TO_APP', 'CLOSE', 'CONTROL_AUDIO', 'CONTROL_DISPLAY',
                        'CONTROL_INPUT_JOYSTICK', 'CONTROL_INPUT_MEDIA_PLAYBACK',
                        'CONTROL_INPUT_MEDIA_RECORDING', 'CONTROL_INPUT_TEXT',
                        'CONTROL_INPUT_TV', 'CONTROL_MOUSE_AND_KEYBOARD',
                        'CONTROL_POWER', 'LAUNCH', 'LAUNCH_WEBAPP', 'READ_APP_STATUS',
                        'READ_COUNTRY_INFO', 'READ_CURRENT_CHANNEL',
                        'READ_INPUT_DEVICE_LIST', 'READ_INSTALLED_APPS',
                        'READ_LGE_SDX', 'READ_LGE_TV_INPUT_EVENTS',
                        'READ_NETWORK_STATE', 'READ_NOTIFICATIONS', 'READ_POWER_STATE',
                        'READ_RUNNING_APPS', 'READ_TV_CHANNEL_LIST',
                        'READ_TV_CURRENT_TIME', 'READ_UPDATE_INFO', 'SEARCH',
                        'TEST_OPEN', 'TEST_PROTECTED', 'TEST_SECURE',
                        'UPDATE_FROM_REMOTE_APP', 'WRITE_NOTIFICATION_ALERT',
                        'WRITE_NOTIFICATION_TOAST', 'WRITE_SETTINGS'
                    ]
                }
            }
        }

        if client_key is not None:
            # add client-key to dictionary
            pairing_request['payload']['client-key'] = client_key

        return json.dumps(pairing_request)

    def connect(self, host, app_name="Python Remote", connect_input_pointer=True):
        # type: (str) -> bool
        if self.is_connected():
            return True

        if self.wsocket is not None and self.wsocket.connected:
            self.wsocket.close()
        self._disconnect_input_pointer()

        self.is_paired = False

        if not isinstance(host, basestring):
            self.log("host is no instance of str: '" + str(host) + "'")
            return False

        host = self._sanitize_host_string(host)
        self.log("Connecting to", host)
        self.last_host = host

        # some prefix made of 6 hex chars from a random UUID
        self.random_prefix = uuid.uuid4().hex[:6] + "_"
        self.command_counter = 0

        msg_id = self.random_prefix + str(self.command_counter)
        self.command_counter += 1

        self.wsocket = websocket.create_connection(host)

        self.pairing_key = self.key_manager.load_client_key(host)
        if self.pairing_key is None:
            self.log("Pairing without key...")
        else:
            self.log("Pairing with key", self.pairing_key)

        pairing_request = self._generate_pairing_request(msg_id, app_name, self.pairing_key)
        self.wsocket.send(pairing_request)

        try:
            received = self.wsocket.recv()
            response = json.loads(received)
        except Exception as e:
            self.log("Could not decode response '" + str(received) + "' received after sending pairing request:" + str(e))
            return False

        if response.get('id') != msg_id:
            self.log("Expected response with ID", msg_id, "but got", response.get('id'))
            return False
        if 'payload' not in response or not isinstance(response['payload'], dict):
            self.log("payload missing in response")
            return False

        if 'pairingType' in response['payload']:
            # not paired yet, next message will be pairing status
            # so load another message
            try:
                received = self.wsocket.recv()
                response = json.loads(received)
            except Exception as e:
                self.log("Could not decode response '" + str(received) + "' received as second message after sending pairing request:" + str(e))
                return False

        if response.get('id') != msg_id:
            self.log("Expected response with ID", msg_id, "but got", response.get('id'))
            return False
        if 'payload' not in response or not isinstance(response['payload'], dict):
            self.log("payload missing in response")
            return False

        if response.get('type') in [None, 'error']: # type missing or {"type": "error"}
            if 'error' in response:
                self.log("Connect failed:", response['error'])
            else:
                self.log("type missing in response")
            return False
        if response['type'] != 'registered':
            self.log("Got different message than expeced: type is", response['type'])
            return False

        key = response['payload'].get('client-key')
        if key is not None and key != self.pairing_key:
            # different client-key than before, save it
            self.pairing_key = key
            self.log("Saving key", self.pairing_key)
            self.key_manager.save_client_key(host, self.pairing_key)

        self.is_paired = True

        if connect_input_pointer:
            # finally connect to InputPointer socket
            self._connect_input_pointer()

        return True

    def disconnect(self):
        # type: () -> ()
        self._disconnect_input_pointer()

        self.is_paired = False

        if not self.is_connected():
            return

        self.wsocket.close()
        self.wsocket = None

    def _connect_input_pointer(self):
        # type: () -> bool
        if self._is_pointer_connected():
            return True

        # get address of input pointer socket
        success, payload = self._send_command("ssap://com.webos.service.networkinput/getPointerInputSocket")

        if not success:
            self.log("Could not connect to InputPointer socket:", payload)
            return False
        if 'socketPath' not in payload:
            self.log("Could not connect to InputPointer socket: socketPath is missing in payload")
            return False

        try:
            self.log("Connecting to InputPointer socket at", payload['socketPath'])
            self.pointer_socket = websocket.create_connection(payload['socketPath'])
        except Exception as e:
            self.log("Connection to InputPointer socket failed:", str(e))
            return False

        return True

    def _disconnect_input_pointer(self):
        # type: () -> ()
        if not self._is_pointer_connected():
            return

        self.pointer_socket.close()
        self.pointer_socket = None

    def _send_command(self, uri, payload=None, resending=False):
        # type: (str, Any) -> (bool, Any)
        # Tuple's second component is dict if first component is True.
        if not self.is_connected():
            if self.last_host is None:
                return (False, "Not connected")
            if not self.connect(self.last_host):
                return (False, "Not connected, reconnect failed")
            if not self.is_connected():
                return (False, "is_connected() returned False after successful reconnect")
            self.log("Successfully reconnected")

        msg_id = self.random_prefix + str(self.command_counter)
        self.command_counter += 1

        msg = {
            'id': msg_id,
            'type': 'request',
            'uri': uri
        }
        if payload is not None:
            msg['payload'] = payload

        self.wsocket.send(json.dumps(msg))

        received = self.wsocket.recv()
        if len(received) == 0 or not self.wsocket.connected:
            if not resending:
                self.log("Connection closed by server, probably timed out.")
                # try connecting one more time
                return self._send_command(uri, payload, resending=True)
            self.log("Connection closed by server, probably timed out  (second time, not trying again).")
            return (False, "Connection closed by server, probably timed out (second time, not trying again).")

        try:
            response = json.loads(received)
        except Exception as e:
            return (False, "Could not decode response '" + str(received) + "' received after sending command:" + str(e))

        if response.get('id') != msg_id:
            return (False, "Response does not match sent message id. Response order might be mismatched. We're screwed.")

        if response.get('type') == 'error':
            return (False, response['error'])

        if 'payload' not in response:
            return (False, "payload missing in response")

        if not isinstance(response['payload'], dict):
            return (False, "payload is no dictionary")

        return (True, response['payload'])

    def toast(self, msg, icon_file=None, file_extension=None, icon_base64=None):
        # type: (str, str, str, str) -> (bool, Any)
        # icon should be approx. 80x80 pixels, bigger icons might be
        # ignored (resulting in blank toast icons) or the toast might fail
        # completely. PNG and JPG have been successfully tested.
        #
        # icon_base64 takes precedence over icon_file if file_extension is given,
        # otherwise icon_file is used, using the file's extension if
        # file_extension is empty.
        if len(msg) > 60:
            self.log("Warning: Toast message is longer than 60 chars")

        if isinstance(icon_base64, basestring) and isinstance(file_extension, basestring):
            encoded_icon = icon_base64
        elif isinstance(icon_file, basestring):
            try:
                with open(icon_file, "rb") as f:
                    encoded_icon = base64.b64encode(f.read()).decode("utf8")
                    if not file_extension:
                        file_extension = icon_file.split(".")[-1]
            except Exception as e:
                return (False, "Encoding icon failed: " + str(e))
        else:
            encoded_icon = None

        payload = {
            # see https://webos-devrel.github.io/webOS.js/notification.js.html
            # for additional information
            'message': msg
        }

        if encoded_icon:
            payload['iconData'] = encoded_icon
            payload['iconExtension'] = file_extension.lower()

        return self._send_command("ssap://system.notifications/createToast", payload)

    def disable_3D(self):
        # type: () -> (bool, Any)
        return self._send_command("ssap://com.webos.service.tv.display/set3DOff")

    def enable_3D(self):
        # type: () -> (bool, Any)
        return self._send_command("ssap://com.webos.service.tv.display/set3DOn")

    def get_3D_Mode(self):
        # type: () -> Display3dMode
        success, payload = self._send_command("ssap://com.webos.service.tv.display/get3DStatus")
        if not success:
            self.log("get_3D_Mode: Could not get current 3D mode:", payload)
            return Display3dMode.ERROR
        return Display3dMode.from_string(payload.get('status3D', {}).get('pattern'))

    def send_enter_key(self):
        # type: () -> (bool, Any)
        return self._send_command("ssap://com.webos.service.ime/sendEnterKey")

    def set_3D_Mode(self, mode):
        # type: (Display3dMode, float) -> (bool, Any)
        if mode < Display3dMode.OFF or mode > Display3dMode.LINE_INTERLEAVE_HALF:
            return (False, "Invalid 3D mode")
        current_mode = self.get_3D_Mode()
        if current_mode == mode:
            return (True, "")
        if current_mode == Display3dMode.ERROR:
            return (False, "set_3D_Mode: Could not get current 3D mode. Something went wrong.")

        if mode == Display3dMode.OFF:
            # simply disable 3D
            return self.disable_3D()

        if current_mode != Display3dMode.OFF:
            # first disable 3D so that we will get the enable-menu when pressing the 3D button
            if not self.disable_3D()[0]:
                return (False, "Could not disable 3D first.")
        else:
            # currently in 2D. Enable 3D to see which 3D mode was saved and disable it again
            self.enable_3D()
            current_mode = self.get_3D_Mode()
            if current_mode == mode:
                # saved mode was correct
                return (True, "")
            self.disable_3D()

        # now the following holds:
        # we want to switch to a specific 3D mode and current_mode holds
        # the mode that the TV will initially switch to when enabling 3D via
        # remote control.

        time.sleep(0.25) # just to make sure
        # enable 3D
        self.send_button(RemoteButton.MODE_3D)
        # about 1 second seems to be minimum, 1.5 just to make sure.
        time.sleep(1.5)

        delta = mode - current_mode
        if delta < 0:
            button = RemoteButton.LEFT
            delta = -delta
        else:
            button = RemoteButton.RIGHT

        for i in range(delta):
            self.send_button(button)

        time.sleep(0.25)
        current_mode = self.get_3D_Mode()
        if current_mode == mode:
            # timing worked
            self.send_click() # close menu
            return (True, "")

        if current_mode == Display3dMode.OFF:
            # shouldn't happen?!
            self.send_click() # close menu
            return (False, "Sending remote buttons resulted in 3D turned off.")
        if current_mode == Display3dMode.ERROR:
            self.send_click() # close menu
            return (False, "Could not get current 3D mode. Something went wrong.")

        # we're not in the correct mode, try one last time
        time.sleep(2)
        delta = mode - current_mode
        if delta < 0:
            button = RemoteButton.LEFT
            delta = -delta
        else:
            button = RemoteButton.RIGHT

        for i in range(delta):
            self.send_button(button)

        time.sleep(0.25)
        self.send_click() # close menu

        # just to make sure
        time.sleep(0.25)
        if self.get_3D_Mode() == mode:
            return (True, "")

        return (False, "Sending remote buttons didn't result in correct 3D mode.")

    def _send_input_command(self, cmd):
        # type: (str) -> (bool, str)
        if not self._is_pointer_connected() and not self._connect_input_pointer():
            return (False, "Could not connect to InputPointer socket")

        self.pointer_socket.send(cmd)
        return (True, "")

    def send_button(self, button):
        # type: (RemoteButton) -> (bool, str)
        return self._send_input_command("type:button\nname:" + button + "\n\n")

    def send_click(self):
        # type: () -> (bool, str)
        return self._send_input_command("type:click\n\n")

    def get_inputs(self):
        # type: () -> (bool, Any)
        success, payload = self._send_command("ssap://tv/getExternalInputList")
        if not success:
            return (False, payload)
        if 'devices' not in payload:
            return (False, "devices missing in payload")

        # polish the list
        devices = payload['devices']
        result = {}

        for dev in devices:
            if 'id' not in dev:
                continue
            result[dev['id']] = {
                'icon': dev.get('icon', 'MISSING'),
                'label': dev.get('label', 'MISSING'),
                'favorite': dev.get('favorite', False)
            }

        return (success, result)

    def set_input(self, input):
        # type: (str) -> (bool, Any)
        # input can be HDMI_1, HDMI_2 etc.
        return self._send_command("ssap://tv/switchInput", {'inputId': input})

    def get_channel(self):
        # type: () -> (bool, Any)
        return self._send_command("ssap://tv/getCurrentChannel")

    def get_volume(self):
        # type: () -> (bool, int)
        # returns (success, volume).
        # if volume is muted or unavailable (optical output etc.), volume
        # will be -1.
        # On error, volume will be -2.
        success, payload = self._send_command("ssap://audio/getVolume")

        if not success:
            return (False, -2)

        if 'volume' in payload:
            return (True, payload['volume'])
        return (False, -2)

    def set_volume(self, volume):
        # type: (int) -> (bool, Any)
        if volume < 0 or volume > 100:
            return (False, "0 <= volume <= 100 must hold.")
        return self._send_command("ssap://audio/setVolume", {'volume': volume})

    def get_audio_status(self):
        # type: () -> (bool, Any)
        # example:
        # {'scenario': 'mastervolume_ext_speaker_optical', 'volume': -1, 'mute': False, 'returnValue': True}
        return self._send_command("ssap://audio/getStatus")

    def send_pong(self):
        if not self.is_connected():
            return False
        self.wsocket.pong(b"")
        return True
