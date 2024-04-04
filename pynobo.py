import asyncio
import collections
from contextlib import suppress
import datetime
import errno
import logging
import threading
import warnings
import socket
from typing import Union

_LOGGER = logging.getLogger(__name__)

# In case any of these errors occurs after successful initial connection, we will try to reconnect.
RECONNECT_ERRORS = [
    errno.ECONNRESET,   # Happens after 24 hours
    errno.ECONNREFUSED, # Not experienced, but likable to happen in case a reboot of the hub
    errno.EHOSTUNREACH, # May happen if hub or network switch is temporarily down
    errno.EHOSTDOWN,    # May happen if hub is temporarily down
    errno.ENETDOWN,     # May happen if local network is temporarily down
    errno.ENETUNREACH,  # May happen if hub or local network is temporarily down
    errno.ETIMEDOUT,    # Happens if hub has not responded to handshake in 60 seconds, e.g. due to network issue
]

class nobo:
    """This is where all the Nobø Hub magic happens!"""

    class API:
        """
        All the commands and responses from API v1.1.
        Some with sensible names, others not yet given better names.
        """

        VERSION = '1.1'

        START = 'HELLO'             #HELLO <version of command set> <Hub s.no.> <date and time in format 'yyyyMMddHHmmss'>
        REJECT = 'REJECT'           #REJECT <reject code>
        HANDSHAKE = 'HANDSHAKE'     #HANDSHAKE

        ADD_ZONE = 'A00'            # Adds Zone to hub database: A00 <Zone id> <Name> <Active week profile id> <Comfort temperature> <Eco temperature> <Allow overrides> <Active override id>
        ADD_COMPONENT = 'A01'       # Adds Component to hub database: A01 <Serial  number>  <Status> <Name> <Reverse on/off?> <Zoneld> <Active override Id> <Temperature sensor for zone>
        ADD_WEEK_PROFILE = 'A02'    # Adds Week Profile to hub database: A02 <Week profile id> <Name> <Profile>
        ADD_OVERRIDE = 'A03'        # Adds an override to hub database: A03 <Id> <Mode> <Type> <End time> <Start time> <Override target> <Override target ID>
        RESPONSE_ADD_ZONE = 'B00'
        RESPONSE_ADD_COMPONENT = 'B01'
        RESPONSE_ADD_WEEK_PROFILE = 'B02'
        RESPONSE_ADD_OVERRIDE = 'B03'

        UPDATE_ZONE = 'U00'             # Updates Zone to hub database: U00 <Zone id> <Name> <Active week profile id> <Comfort temperature> <Eco temperature> <Allow overrides> <Active override id>
        UPDATE_COMPONENT = 'U01'        # Updates Component to hub database: U01 <Serial number> <Status> <Name> <Reverse on/off?> <Zoneld> <Active override Id> <Temperature sensor for zone>
        UPDATE_WEEK_PROFILE = 'U02'     # Updates Week Profile to hub database: U02 <Week profile id> <Name> <Profile>
        UPDATE_HUB_INFO = 'U03'         # Updates hub information: U83 <Snr> <Name> <DefaultAwayOverrideLength> <ActiveOverrideid> <Softwareversion> <Hardwareversion> <Producti????
        UPDATE_INTERNET_ACCESS = 'U06'  # Updates hub internet connectivity function and encryption key (LAN only): U86 <Enable internet access> <Encryption key> <Reserved 1> <Reserved 2>
        RESPONSE_UPDATE_ZONE = 'V00'
        RESPONSE_UPDATE_COMPONENT = 'V01'
        RESPONSE_UPDATE_WEEK_PROFILE = 'V02'
        RESPONSE_UPDATE_HUB_INFO = 'V03'
        RESPONSE_UPDATE_INTERNET_ACCESS = 'V06'

        # Removes a Zone from the hub's internal database. All values except Zone lD is ignored.
        # Any Components in the Zone are also deleted (and S02 Component deleted messages arc sent for the deleted Components).
        # Any Component used as temperature sensor for the Zone is modified to no longer be temperature sensor for the Zone (and a V0l Component updated message is sent).
        # R00 <Zone id> <Name> <Active week profile id> <Comfort temperature> <Eco temperature> <Allow overrides> <Active override id>
        REMOVE_ZONE = 'R00'

        # Removes a Component from the hub's internal database. All values except Component Serial Number is ignored.
        # R01 <Serial number> <Status> <Name> <Reverse on/off?> <Zoneid> <Active override Id> <Temperature sensor for zone>
        REMOVE_COMPONENT = 'R01'

        # Removes a WeekProfile from the hub's intemal  database. All values except  Week Profile lD is ignored.
        # Any Zones that are set to use the Week Profile are set to use the default Week Profile in stead (and V00 Zone updated messages are sent).
        # R02 <Week profile id> <Name> <Profile>
        REMOVE_WEEK_PROFILE = 'R02'

        RESPONSE_REMOVE_ZONE = 'S00'
        RESPONSE_REMOVE_COMPONENT = 'S01'
        RESPONSE_REMOVE_WEEK_PROFILE = 'S02'
        RESPONSE_REMOVE_OVERRIDE = 'S03'

        # Gets all information from hub. Will trigger a sequence  of series of one HOO message, zero or more
        # HOI, zero or more H02, zero or more Y02, zero or more H03, zero or more H04 commands, one V06
        # message if <.:onne<.:ted v ia LAN (not Internet), and lastly a H05 message. 'll1e client  knows
        # that the Hub is tlnished  sending all info when it has received  the H05 mess3ge.
        GET_ALL_INFO = 'G00'

        # (Never  used by the Nobo Energy  Control app- you should only use GOO.) Gets all Zones lrom hub.
        # Will trigger a series of H01 messages from the Hub.
        GET_ALL_ZONES = 'G01'

        # (Never  used by the Nobo Energy  Control app - you should only use GOO.) Gets all Components li·om hub.
        # Will result i n a series of H02 messages  from the Hub.
        GET_ALL_COMPONENTS = 'G02'

        # (Never used by the Nobo Energy Control app- you should only use GOO.) Gets all WeekProfile data from hub.
        # Will trigger a series of 1103 messages from the lluh.
        GET_ALL_WEEK_PROFILES = 'G03'

        # (Never used by the Nobo Energy Control app - you should only use GOO.) Gets all active overrrides from hub.
        # Will trigger a series of H04 messages from the Hub.
        GET_ACTIVE_OVERRIDES = 'G04'

        RESPONSE_SENDING_ALL_INFO = 'H00'   # Response to GET_ALL_INFO signifying that all relevant info stored in Hub is about to be sent.
        RESPONSE_ZONE_INFO = 'H01'          # Response with Zone info, one per message: H01 <Zone id> <Name> <Active week profile id> <Comfort temperature> <Eco temperature> <Allow overrides> <Active override id>
        RESPONSE_COMPONENT_INFO = 'H02'     # Response with Component info, one per message: H02 <Serial number> <Status> <Name> <Reverse on/off?> <Zoneld> <Active override Id> <Temperature sensor for zone>
        RESPONSE_WEEK_PROFILE_INFO = 'H03'  # Response with Week Profile info, one per message: H03 <Week profile id> <Name> <Profile>
        RESPONSE_OVERRIDE_INFO = 'H04'      # Response with override info, one per message: H04 <Id> <Mode> <Type> <End time> <Start time> <Override target> <Override target ID>
        RESPONSE_HUB_INFO = 'H05'           # G00 request complete signal + static info: H05 <Snr> <Name> <DefaultAwayOverrideLength> <ActiveOverrideid> <SoftwareVersion> <HardwareVersion> <ProductionDate>

        EXECUTE_START_SEARCH = 'X00'
        EXECUTE_STOP_SEARCH = 'X01'
        EXECUTE_COMPONENT_PAIR = 'X03'
        RESPONSE_STARTED_SEARCH = 'Y00'
        RESPONSE_STOPPED_SEARCH = 'Y01'
        RESPONSE_COMPONENT_TEMP = 'Y02'     # Component temperature value sent as part of a GOO response, or pushed from the Hub automatically to all connected clients whenever the Hub has received updated temperature data.
        RESPONSE_COMPONENT_PAIR = 'Y03'
        RESPONSE_COMPONENT_FOUND = 'Y04'

        RESPONSE_ERROR = 'E00'              # Other error messages than E00 may also be sent from the Hub (E01, E02 etc.): E00 <command> <message>

        OVERRIDE_MODE_NORMAL = '0'
        OVERRIDE_MODE_COMFORT = '1'
        OVERRIDE_MODE_ECO = '2'
        OVERRIDE_MODE_AWAY = '3'
        OVERRIDE_MODES = [OVERRIDE_MODE_NORMAL, OVERRIDE_MODE_COMFORT, OVERRIDE_MODE_ECO, OVERRIDE_MODE_AWAY]

        OVERRIDE_TYPE_NOW = '0'
        OVERRIDE_TYPE_TIMER = '1'
        OVERRIDE_TYPE_FROM_TO = '2'
        OVERRIDE_TYPE_CONSTANT = '3'
        OVERRIDE_TYPES = [OVERRIDE_TYPE_NOW, OVERRIDE_TYPE_TIMER, OVERRIDE_TYPE_FROM_TO, OVERRIDE_TYPE_CONSTANT]

        OVERRIDE_TARGET_GLOBAL = '0'
        OVERRIDE_TARGET_ZONE = '1'
        OVERRIDE_TARGET_COMPONENT = '2'     # Not implemented yet
        OVERRIDE_TARGETS = [OVERRIDE_TARGET_GLOBAL, OVERRIDE_TARGET_ZONE, OVERRIDE_TARGET_COMPONENT]

        OVERRIDE_NOT_ALLOWED = '0'
        OVERRIDE_ALLOWED = '1'

        OVERRIDE_ID_NONE = '-1'
        OVERRIDE_ID_HUB = '-1'

        WEEK_PROFILE_STATE_ECO = '0'
        WEEK_PROFILE_STATE_COMFORT = '1'
        WEEK_PROFILE_STATE_AWAY = '2'
        WEEK_PROFILE_STATE_OFF = '4'

        STRUCT_KEYS_HUB = ['serial', 'name', 'default_away_override_length', 'override_id', 'software_version', 'hardware_version', 'production_date']
        STRUCT_KEYS_ZONE = ['zone_id', 'name', 'week_profile_id', 'temp_comfort_c', 'temp_eco_c', 'override_allowed', 'deprecated_override_id']
        STRUCT_KEYS_COMPONENT = ['serial', 'status', 'name', 'reverse_onoff', 'zone_id', 'override_id', 'tempsensor_for_zone_id']
        STRUCT_KEYS_WEEK_PROFILE = ['week_profile_id', 'name', 'profile'] # profile is minimum 7 and probably more values separated by comma
        STRUCT_KEYS_OVERRIDE = ['override_id', 'mode', 'type', 'end_time', 'start_time', 'target_type', 'target_id']

        NAME_OFF = 'off'
        NAME_AWAY = 'away'
        NAME_ECO = 'eco'
        NAME_COMFORT = 'comfort'
        NAME_NORMAL = 'normal'

        DICT_OVERRIDE_MODE_TO_NAME = {OVERRIDE_MODE_NORMAL : NAME_NORMAL, OVERRIDE_MODE_COMFORT : NAME_COMFORT, OVERRIDE_MODE_ECO : NAME_ECO, OVERRIDE_MODE_AWAY : NAME_AWAY}
        DICT_WEEK_PROFILE_STATUS_TO_NAME = {WEEK_PROFILE_STATE_ECO : NAME_ECO, WEEK_PROFILE_STATE_COMFORT : NAME_COMFORT, WEEK_PROFILE_STATE_AWAY : NAME_AWAY, WEEK_PROFILE_STATE_OFF : NAME_OFF}
        DICT_NAME_TO_OVERRIDE_MODE = {NAME_NORMAL : OVERRIDE_MODE_NORMAL, NAME_COMFORT : OVERRIDE_MODE_COMFORT, NAME_ECO : OVERRIDE_MODE_ECO, NAME_AWAY : OVERRIDE_MODE_AWAY}
        DICT_NAME_TO_WEEK_PROFILE_STATUS = {NAME_ECO : WEEK_PROFILE_STATE_ECO, NAME_COMFORT : WEEK_PROFILE_STATE_COMFORT, NAME_AWAY : WEEK_PROFILE_STATE_AWAY, NAME_OFF : WEEK_PROFILE_STATE_OFF}

        def is_valid_datetime(timestamp: str):
            if len(timestamp) != 12:
                # Leading zero is optional for some of the fields below, but we require it.
                return False
            try:
                datetime.datetime.strptime(timestamp, '%Y%m%d%H%M')
            except ValueError:
                return False
            return True

        def time_is_quarter(minutes: str):
            return int(minutes) % 15 == 0

        def validate_temperature(temperature: Union[int, str]):
            if type(temperature) not in (int, str):
                raise TypeError('Temperature must be integer or string')
            if isinstance(temperature, str) and not temperature.isdigit():
                raise ValueError(f'Temperature "{temperature}" must be digits')
            temperature_int = int(temperature)
            if temperature_int < 7:
                raise ValueError(f'Min temperature is 7°C')
            if temperature_int > 30:
                raise ValueError(f'Max temperature is 30°C')

        def validate_week_profile(profile):
            if type(profile) != list:
                raise ValueError("Week profile must be a list")
            day_count=0
            for i in profile:
                if len(i) != 5:
                    raise ValueError(f"Invalid week profile entry: {i}")
                time = datetime.datetime.strptime(i[0:4], "%H%M")
                if not time.minute % 15 == 0:
                    raise ValueError(f"Week profile entry not in whole quarters: {i}")
                # Last character is state (0=Eco, 1=Comfort, 2=Away, 4=Off)
                if not i[4] in "0124":
                    raise ValueError(f"Week profile entry contains invalid state, must be 0, 1, 2, or 4: {i}")
                if time.hour == 0 and time.minute == 0:
                    day_count+=1
            if day_count != 7:
                raise ValueError("Week profile must contain exactly 7 entries for midnight (starting with 0000)")


    class Model:
        """
        A device model that supports Nobø Ecohub.

        Official lists of devices:
        https://help.nobo.no/en/user-manual/before-you-start/what-is-a-receiver/list-of-receivers/
        https://help.nobo.no/en/user-manual/before-you-start/what-is-a-transmitter/list-of-transmitters/
        """

        THERMOSTAT_HEATER = "THERMOSTAT_HEATER"
        THERMOSTAT_FLOOR = "THERMOSTAT_FLOOR"
        THERMOSTAT_ROOM = "THERMOSTAT_ROOM"
        SWITCH = "SWITCH"
        SWITCH_OUTLET = "SWITCH_OUTLET"
        CONTROL_PANEL = "CONTROL_PANEL"
        UNKNOWN = "UNKNOWN"

        def __init__(
                self,
                model_id: str,
                type: Union[THERMOSTAT_HEATER, THERMOSTAT_FLOOR, THERMOSTAT_ROOM, SWITCH, SWITCH_OUTLET, CONTROL_PANEL, UNKNOWN],
                name: str,
                *,
                supports_comfort: bool = False,
                supports_eco: bool = False,
                requires_control_panel = False,
                has_temp_sensor: bool = False):
            self._model_id = model_id
            self._type = type
            self._name = name
            self._supports_comfort = supports_comfort
            self._supports_eco = supports_eco
            self._requires_control_panel = requires_control_panel
            self._has_temp_sensor = has_temp_sensor

        @property
        def model_id(self) -> str:
            """Model id of the component (first 3 digits of the serial number)."""
            return self._model_id

        @property
        def name(self) -> str:
            """Model name."""
            return self._name

        @property
        def type(self) -> Union[THERMOSTAT_HEATER, THERMOSTAT_FLOOR, THERMOSTAT_ROOM, SWITCH, SWITCH_OUTLET, CONTROL_PANEL, UNKNOWN]:
            """Model type."""
            return self._type

        @property
        def supports_comfort(self) -> bool:
            """Return True if comfort temperature can be set on hub."""
            return self._supports_comfort

        @property
        def supports_eco(self) -> bool:
            """Return True if eco temperature can be set on hub."""
            return self._supports_eco

        @property
        def requires_control_panel(self) -> bool:
            """Return True if setting temperature on hub requires a control panel in the zone."""
            return self._requires_control_panel

        @property
        def has_temp_sensor(self) -> bool:
            """Return True if component has a temperature sensor."""
            return self._has_temp_sensor

    MODELS = {
        "120": Model("120", Model.SWITCH, "RS 700"),
        "121": Model("121", Model.SWITCH, "RSX 700"),
        "130": Model("130", Model.SWITCH_OUTLET, "RCE 700"),
        "160": Model("160", Model.THERMOSTAT_HEATER, "R80 RDC 700"),
        "165": Model("165", Model.THERMOSTAT_HEATER, "R80 RDC 700 LST (GB)"),
        "168": Model("168", Model.THERMOSTAT_HEATER, "NCU-2R", supports_comfort=True, supports_eco=True),
        "169": Model("169", Model.THERMOSTAT_HEATER, "DCU-2R", supports_comfort=True, supports_eco=True),
        "170": Model("170", Model.THERMOSTAT_HEATER, "Serie 18, ewt touch", supports_comfort=True, supports_eco=True), # Not verified if temperature can be set remotely
        "180": Model("180", Model.THERMOSTAT_HEATER, "2NC9 700", supports_eco=True),
        "182": Model("182", Model.THERMOSTAT_HEATER, "R80 RSC 700 (5-24)", supports_eco=True),
        "183": Model("183", Model.THERMOSTAT_HEATER, "R80 RSC 700 (5-30)", supports_eco=True),
        "184": Model("184", Model.THERMOSTAT_HEATER, "NCU-1R", supports_eco=True),
        "186": Model("186", Model.THERMOSTAT_HEATER, "DCU-1R", supports_eco=True),
        "190": Model("190", Model.THERMOSTAT_HEATER, "Safir", supports_comfort=True, supports_eco=True, requires_control_panel=True),
        "192": Model("192", Model.THERMOSTAT_HEATER, "R80 TXF 700", supports_comfort=True, supports_eco=True, requires_control_panel=True),
        "194": Model("194", Model.THERMOSTAT_HEATER, "R80 RXC 700", supports_comfort=True, supports_eco=True),
        "198": Model("198", Model.THERMOSTAT_HEATER, "NCU-ER", supports_comfort=True, supports_eco=True),
        "199": Model("199", Model.THERMOSTAT_HEATER, "DCU-ER", supports_comfort=True, supports_eco=True),
        "200": Model("200", Model.THERMOSTAT_FLOOR, "TRB 36 700"),
        "210": Model("210", Model.THERMOSTAT_FLOOR, "NTB-2R", supports_comfort=True, supports_eco=True),
        "220": Model("220", Model.THERMOSTAT_FLOOR, "TR36", supports_eco=True),
        "230": Model("230", Model.THERMOSTAT_ROOM, "TCU 700"),
        "231": Model("231", Model.THERMOSTAT_ROOM, "THB 700"),
        "232": Model("232", Model.THERMOSTAT_ROOM, "TXB 700"),
        "234": Model("234", Model.CONTROL_PANEL, "SW4", has_temp_sensor=True),
    }

    class DiscoveryProtocol(asyncio.DatagramProtocol):
        """Protocol to discover Nobø Echohub on local network."""

        def __init__(self, serial = '', ip = None):
            """
            :param serial: The last 3 digits of the Ecohub serial number or the complete 12 digit serial number
            :param ip: ip address to search for Ecohub at (default None)
            """
            self.serial = serial
            self.ip = ip
            self.hubs = set()

        def connection_made(self, transport: asyncio.transports.DatagramTransport):
            self.transport = transport

        def datagram_received(self, data: bytes, addr):
            msg = data.decode('utf-8')
            _LOGGER.info('broadcast received: %s from %s', msg, addr[0])
            # Expected string “__NOBOHUB__123123123”, where 123123123 is replaced with the first 9 digits of the Hub’s serial number.
            if msg.startswith('__NOBOHUB__'):
                discover_serial = msg[11:]
                discover_ip = addr[0]
                if len(self.serial) == 12:
                    if discover_serial != self.serial[0:9]:
                        # This is not the Ecohub you are looking for
                        discover_serial = None
                    else:
                        discover_serial = self.serial
                else:
                    discover_serial += self.serial
                if self.ip and discover_ip != self.ip:
                    # This is not the Ecohub you are looking for
                    discover_ip = None
                if discover_ip and discover_serial:
                    self.hubs.add( (discover_ip, discover_serial) )

    def __init__(self, serial, ip=None, discover=True, loop=None, synchronous=True, timezone: datetime.tzinfo=None):
        """
        Initialize logger and dictionaries.

        :param serial: The last 3 digits of the Ecohub serial number or the complete 12 digit serial number
        :param ip: IP address to search for Ecohub at (default None)
        :param discover: True/false for using UDP autodiscovery for the IP (default True)
        :param loop: Deprecated
        :param synchronous: True/false for using the module synchronously. For backwards compatibility.
        """

        self.serial = serial
        self.ip = ip
        self.discover = discover
        if loop is not None:
            _LOGGER.warning("loop is deprecated. Use synchronous=False instead.")
            synchronous=False
        self.timezone = timezone

        self._callbacks = []
        self._reader = None
        self._writer = None
        self._keep_alive_task = None
        self._socket_receive_task = None

        self._received_all_info = False
        self.hub_info = {}
        self.zones = collections.OrderedDict()
        self.components = collections.OrderedDict()
        self.week_profiles = collections.OrderedDict()
        self.overrides = collections.OrderedDict()
        self.temperatures = collections.OrderedDict()

        if synchronous:
            # Run asyncio in a separate thread
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                _LOGGER.debug("Creating new event loop")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start())
            _LOGGER.debug("Creating daemon thread")
            thread = threading.Thread(target=lambda: loop.run_forever())
            thread.setDaemon(True)
            thread.start()

    def register_callback(self, callback=lambda *args, **kwargs: None):
        """
        Register a callback to notify updates to the hub state. The callback MUST be safe to call
        from the event loop. The nobo instance is passed to the callback function. Limit callbacks
        to read state.

        :param callback: a callback method
        """
        self._callbacks.append(callback)

    def deregister_callback(self, callback=lambda *args, **kwargs: None):
        """
        Deregister a previously registered callback.

        :param callback: a callback method
        """
        self._callbacks.remove(callback)

    async def connect(self):
        """Connect to Ecohub, either by scanning or directly."""
        connected = False
        if self.discover:
            _LOGGER.info('Looking for Nobø Ecohub with serial: %s and ip: %s', self.serial, self.ip)
            discovered_hubs = await self.async_discover_hubs(serial=self.serial, ip=self.ip)
            if not discovered_hubs:
                _LOGGER.error('Failed to discover any Nobø Ecohubs')
                raise Exception('Failed to discover any Nobø Ecohubs')
            while discovered_hubs:
                (discover_ip, discover_serial) = discovered_hubs.pop()
                connected = await self.async_connect_hub(discover_ip, discover_serial)
                if connected:
                    break  # We connect to the first valid hub, no reason to try the rest
        else:
            # check if we have an IP
            if not self.ip:
                _LOGGER.error('Could not connect, no ip address provided')
                raise ValueError('Could not connect, no ip address provided')

            # check if we have a valid serial before we start connection
            if len(self.serial) != 12:
                _LOGGER.error('Could not connect, no valid serial number provided')
                raise ValueError('Could not connect, no valid serial number provided')

            connected = await self.async_connect_hub(self.ip, self.serial)

        if not connected:
            _LOGGER.error('Could not connect to Nobø Ecohub')
            raise Exception(f'Failed to connect to Nobø Ecohub with serial: {self.serial} and ip: {self.ip}')

    async def start(self):
        """Discover Ecohub and start the TCP client."""

        if not self._writer:
            await self.connect()

        # Start the tasks to send keep-alive and receive data
        self._keep_alive_task = asyncio.create_task(self.keep_alive())
        self._socket_receive_task = asyncio.create_task(self.socket_receive())
        _LOGGER.info('connected to Nobø Ecohub')

    async def stop(self):
        """Stop the keep-alive and receiver tasks and close the connection to Nobø Ecohub."""
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._keep_alive_task
        if self._socket_receive_task:
            self._socket_receive_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._keep_alive_task
        await self.close()
        _LOGGER.info('disconnected from Nobø Ecohub')

    async def close(self):
        """Close the connection to Nobø Ecohub."""
        if self._writer:
            self._writer.close()
            with suppress(ConnectionError):
                await self._writer.wait_closed()
            self._writer = None
            _LOGGER.info('connection closed')

    def connect_hub(self, ip, serial):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.async_connect_hub(ip, serial))

    async def async_connect_hub(self, ip, serial):
        """
        Attempt initial connection and handshake.

        :param ip: The ecohub ip address to connect to
        :param serial: The complete 12 digit serial number of the hub to connect to
        """
        if len(serial) != 12 or not serial.isdigit():
            raise ValueError(f'Invalid serial number: {serial}')

        self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(ip, 27779), timeout=5)

        # start handshake: "HELLO <version of command set> <Hub s.no.> <date and time in format 'yyyyMMddHHmmss'>\r"
        now = datetime.datetime.now(self.timezone).strftime('%Y%m%d%H%M%S')
        await self.async_send_command([nobo.API.START, nobo.API.VERSION, serial, now])

        # receive the response data (4096 is recommended buffer size)
        response = await asyncio.wait_for(self.get_response(), timeout=5)
        _LOGGER.debug('first handshake response: %s', response)

        # successful response is "HELLO <its version of command set>\r"
        if response[0] == nobo.API.START:
            # send “REJECT\r” if command set is not supported? No need to abort if Hub is ok with the mismatch?
            if response[1] != nobo.API.VERSION:
                #await self.async_send_command([nobo.API.REJECT])
                _LOGGER.warning('api version might not match, hub: v%s, pynobo: v%s', response[1], nobo.API.VERSION)
                warnings.warn(f'api version might not match, hub: v{response[1]}, pynobo: v{nobo.API.VERSION}') #overkill?

            # send/receive handshake complete
            await self.async_send_command([nobo.API.HANDSHAKE])
            response = await asyncio.wait_for(self.get_response(), timeout=5)
            _LOGGER.debug('second handshake response: %s', response)

            if response[0] == nobo.API.HANDSHAKE:
                # Connect OK, store full serial for reconnect
                self.hub_ip = ip
                self.hub_serial = serial

                # Get initial data
                await asyncio.wait_for(self._get_initial_data(), timeout=5)
                for callback in self._callbacks:
                    callback(self)
                return True
            else:
                # Something went wrong...
                _LOGGER.error('Final handshake not as expected %s', response)
                await self.close()
                raise Exception(f'Final handshake not as expected {response}')
        if response[0] == nobo.API.REJECT:
            # This may not be the hub we are looking for

            # Reject response: "REJECT <reject code>\r"
            # 0=Client command set version too old (or too new!).
            # 1=Hub serial number mismatch.
            # 2=Wrong number of arguments.
            # 3=Timestamp incorrectly formatted
            _LOGGER.warning('connection to hub rejected: %s', response)
            await self.close()
            return False

        # Unexpected response
        _LOGGER.error('connection to hub rejected: %s', response)
        raise Exception(f'connection to hub rejected: {response}')

    async def reconnect_hub(self):
        """Attempt to reconnect to the hub."""

        _LOGGER.info('reconnecting to hub')
        # Pause keep alive during reconnect
        self._keep_alive = False
        # TODO: set timeout?
        if self.discover:
            # Reconnect using complete serial, but allow ip to change unless originally provided
            discovered_hubs = await self.async_discover_hubs(ip=self.ip, serial=self.hub_serial, rediscover=True)
            while discovered_hubs:
                (discover_ip, discover_serial) = discovered_hubs.pop()
                try:
                    connected = await self.async_connect_hub(discover_ip, discover_serial)
                    if connected:
                        break
                except OSError as e:
                    # We know we should be able to connect, because we just discovered the IP address. However, if
                    # the connection was lost due to network problems on our host, we must wait until we have a local
                    # IP address. E.g. discovery may find Nobø Ecohub before DHCP address is assigned.
                    if e.errno in RECONNECT_ERRORS:
                        _LOGGER.warning("Failed to connect to ip %s: %s", discover_ip, e)
                        discovered_hubs.add( (discover_ip, discover_serial) )
                        await asyncio.sleep(1)
                    else:
                        raise e
        else:
            connected = False
            while not connected:
                _LOGGER.debug('Discovery disabled - waiting 10 seconds before trying to reconnect.')
                await asyncio.sleep(10)
                with suppress(asyncio.TimeoutError):
                    try:
                        connected = await self.async_connect_hub(self.ip, self.serial)
                    except OSError as e:
                        if e.errno in RECONNECT_ERRORS:
                            _LOGGER.debug('Ignoring %s', e)
                        else:
                            raise e

        self._keep_alive = True
        _LOGGER.info('reconnected to Nobø Hub')

    @staticmethod
    def discover_hubs(serial="", ip=None, autodiscover_wait=3.0, loop=None):
        if loop is not None:
            _LOGGER.warning("loop is deprecated")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(nobo.async_discover_hubs(serial, ip, autodiscover_wait))

    @staticmethod
    async def async_discover_hubs(serial="", ip=None, autodiscover_wait=3.0, loop=None, rediscover=False):
        """
        Attempt to autodiscover Nobø Ecohubs on the local network.

        Every two seconds, the Hub sends one UDP broadcast packet on port 10000
        to broadcast IP 255.255.255.255, we listen for this package, and collect
        every packet that contains the magic __NOBOHUB__ identifier. The set
        of (ip, serial) tuples is returned.

        Specifying a complete 12 digit serial number or an ip address, will only
        attempt to discover hubs matching that serial, ip address or both.

        Specifyng the last 3 digits of the serial number will append this to the
        discovered serial number.

        Not specifying serial or ip will include all found hubs on the network,
        but only the discovered part of the serial number (first 9 digits).

        :param serial: The last 3 digits of the Ecohub serial number or the complete 12 digit serial number
        :param ip: ip address to search for Ecohub at (default None)
        :param autodiscover_wait: how long to wait for an autodiscover package from the hub (default 3.0)
        :param loop: deprecated
        :param rediscover: if true, run until the hub is discovered

        :return: a set of hubs matching that serial, ip address or both
        """

        if loop is not None:
            _LOGGER.warning("loop is deprecated.")
        transport, protocol = await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: nobo.DiscoveryProtocol(serial, ip),
            local_addr=('0.0.0.0', 10000),
            reuse_port=nobo._reuse_port())
        try:
            await asyncio.sleep(autodiscover_wait)
            while rediscover and not protocol.hubs:
                await asyncio.sleep(autodiscover_wait)
        finally:
            transport.close()
        return protocol.hubs

    @staticmethod
    def _reuse_port() -> bool:
        """
        Check if we can set `reuse_port` when listening for broadcasts. To support Windows.
        """
        if hasattr(socket, 'SO_REUSEPORT'):
            sock = socket.socket(type=socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                sock.close()
                return True
            except OSError:
                pass
        return False

    async def keep_alive(self, interval = 14):
        """
        Send a periodic handshake. Needs to be sent every < 30 sec, preferably every 14 seconds.

        :param interval: seconds between each handshake. Default 14.
        """
        self._keep_alive = True
        while True:
            await asyncio.sleep(interval)
            if self._keep_alive:
                await self.async_send_command([nobo.API.HANDSHAKE])

    def _create_task(self, target):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.call_soon_threadsafe(lambda: loop.create_task(target))

    def send_command(self, commands):
        self._create_task(self.async_send_command(commands))

    async def async_send_command(self, commands):
        """
        Send a list of command string(s) to the hub.

        :param commands: list of commands, either strings or integers
        """
        if not self._writer:
            return

        _LOGGER.debug('sending: %s', commands)

        # Convert integers to string
        for idx, c in enumerate(commands):
            if isinstance(c, int):
                commands[idx] = str(c)

        message = ' '.join(commands).encode('utf-8')
        try:
            self._writer.write(message + b'\r')
            await self._writer.drain()
        except ConnectionError as e:
            _LOGGER.info('lost connection to hub (%s)', e)
            await self.close()

    async def _get_initial_data(self):
        self._received_all_info = False
        await self.async_send_command([nobo.API.GET_ALL_INFO])
        while not self._received_all_info:
            self.response_handler(await self.get_response())

    async def get_response(self):
        """
        Get a response string from the hub and reformat string list before returning it.

        :return: a single response as a list of strings where each string is a field
        """
        try:
            message = await self._reader.readuntil(b'\r')
            message = message[:-1]
        except ConnectionError as e:
            _LOGGER.info('lost connection to hub (%s)', e)
            await self.close()
            raise e
        response  = message.decode('utf-8').split(' ')
        _LOGGER.debug('received: %s', response)
        return response

    async def socket_receive(self):
        try:
            while True:
                try:
                    response = await self.get_response()
                    if response[0] == nobo.API.HANDSHAKE:
                        pass # Handshake, no action needed
                    elif response[0] == 'E':
                        _LOGGER.error('error! what did you do? %s', response)
                        # TODO: Raise something here?
                    else:
                        self.response_handler(response)
                        for callback in self._callbacks:
                            callback(self)
                except (asyncio.IncompleteReadError) as e:
                    _LOGGER.info('Reconnecting due to %s', e)
                    await self.reconnect_hub()
                except (OSError) as e:
                    if e.errno in RECONNECT_ERRORS:
                        _LOGGER.info('Reconnecting due to %s', e)
                        await self.reconnect_hub()
                    else:
                        raise e
        except asyncio.CancelledError:
            _LOGGER.debug('socket_receive stopped')
        except Exception as e:
            # Ops, now we have real problems
            _LOGGER.error('Unhandled exception %s', e, exc_info=1)
            # Just disconnect (instead of risking an infinite reconnect loop)
            await self.stop()

    def response_handler(self, response):
        """
        Handle the response(s) from the hub and update the dictionaries accordingly.

        :param response: list of strings where each string is a field
        """

        # All info incoming, clear existing info
        if response[0] == nobo.API.RESPONSE_SENDING_ALL_INFO:
            self._received_all_info = False
            self.hub_info = {}
            self.zones = {}
            self.components = {}
            self.week_profiles = {}
            self.overrides = {}

        # The added/updated info messages
        elif response[0] in [nobo.API.RESPONSE_ZONE_INFO, nobo.API.RESPONSE_ADD_ZONE , nobo.API.RESPONSE_UPDATE_ZONE]:
            dicti = collections.OrderedDict(zip(nobo.API.STRUCT_KEYS_ZONE, response[1:]))
            self.zones[dicti['zone_id']] = dicti
            _LOGGER.info('added/updated zone: %s', dicti['name'])

        elif response[0] in [nobo.API.RESPONSE_COMPONENT_INFO, nobo.API.RESPONSE_ADD_COMPONENT , nobo.API.RESPONSE_UPDATE_COMPONENT]:
            dicti = collections.OrderedDict(zip(nobo.API.STRUCT_KEYS_COMPONENT, response[1:]))
            if dicti['zone_id'] == '-1' and dicti['tempsensor_for_zone_id'] != '-1':
                dicti['zone_id'] = dicti['tempsensor_for_zone_id']
            serial = dicti['serial']
            model_id = serial[:3]
            if model_id in nobo.MODELS:
                dicti['model'] = nobo.MODELS[model_id]
            else:
                dicti['model'] = nobo.Model(
                    model_id,
                    nobo.Model.UNKNOWN,
                    f'Unknown (serial number: {serial[:3]} {serial[3:6]} {serial[6:9]} {serial[9:]})'
                )
            self.components[dicti['serial']] = dicti
            _LOGGER.info('added/updated component: %s', dicti['name'])

        elif response[0] in [nobo.API.RESPONSE_WEEK_PROFILE_INFO, nobo.API.RESPONSE_ADD_WEEK_PROFILE, nobo.API.RESPONSE_UPDATE_WEEK_PROFILE]:
            dicti = collections.OrderedDict(zip(nobo.API.STRUCT_KEYS_WEEK_PROFILE, response[1:]))
            dicti['profile'] = response[-1].split(',')
            self.week_profiles[dicti['week_profile_id']] = dicti
            _LOGGER.info('added/updated week profile: %s', dicti['name'])

        elif response[0] in [nobo.API.RESPONSE_OVERRIDE_INFO, nobo.API.RESPONSE_ADD_OVERRIDE]:
            dicti = collections.OrderedDict(zip(nobo.API.STRUCT_KEYS_OVERRIDE, response[1:]))
            self.overrides[dicti['override_id']] = dicti
            _LOGGER.info('added/updated override: id %s', dicti['override_id'])

        elif response[0] in [nobo.API.RESPONSE_HUB_INFO, nobo.API.RESPONSE_UPDATE_HUB_INFO]:
            self.hub_info = collections.OrderedDict(zip(nobo.API.STRUCT_KEYS_HUB, response[1:]))
            _LOGGER.info('updated hub info: %s', self.hub_info)
            if response[0] == nobo.API.RESPONSE_HUB_INFO:
                self._received_all_info = True

        # The removed info messages
        elif response[0] == nobo.API.RESPONSE_REMOVE_ZONE:
            dicti = collections.OrderedDict(zip(nobo.API.STRUCT_KEYS_ZONE, response[1:]))
            self.zones.pop(dicti['zone_id'], None)
            _LOGGER.info('removed zone: %s', dicti['name'])

        elif response[0] == nobo.API.RESPONSE_REMOVE_COMPONENT:
            dicti = collections.OrderedDict(zip(nobo.API.STRUCT_KEYS_COMPONENT, response[1:]))
            self.components.pop(dicti['serial'], None)
            _LOGGER.info('removed component: %s', dicti['name'])

        elif response[0] == nobo.API.RESPONSE_REMOVE_WEEK_PROFILE:
            dicti = collections.OrderedDict(zip(nobo.API.STRUCT_KEYS_WEEK_PROFILE, response[1:]))
            self.week_profiles.pop(dicti['week_profile_id'], None)
            _LOGGER.info('removed week profile: %s', dicti['name'])

        elif response[0] == nobo.API.RESPONSE_REMOVE_OVERRIDE:
            dicti = collections.OrderedDict(zip(nobo.API.STRUCT_KEYS_OVERRIDE, response[1:]))
            self.overrides.pop(dicti['override_id'], None)
            _LOGGER.info('removed override: %s', dicti['override_id'])

        # Component temperature data
        elif response[0] == nobo.API.RESPONSE_COMPONENT_TEMP:
            self.temperatures[response[1]] = response[2]
            _LOGGER.info('updated temperature from %s: %s', response[1], response[2])

        # Internet settings
        elif response[0] == nobo.API.RESPONSE_UPDATE_INTERNET_ACCESS:
            internet_access = response[1]
            encryption_key = 0
            for i in range(2, 18):
                encryption_key = (encryption_key << 8) + int(response[i])
            _LOGGER.info('internet enabled: %s, key: %s', internet_access, hex(encryption_key))

        else:
            _LOGGER.warning('behavior undefined for this response: %s', response)
            warnings.warn(f'behavior undefined for this response: {response}') #overkill?

    def create_override(self, mode, type, target_type, target_id='-1', end_time='-1', start_time='-1'):
        self._create_task(self.async_create_override(mode, type, target_type, target_id, end_time, start_time))

    async def async_create_override(self, mode, type, target_type, target_id='-1', end_time='-1', start_time='-1'):
        """
        Override hub/zones/components. Use OVERRIDE_MODE_NORMAL to disable an existing override.

        :param mode: API.OVERRIDE_MODE. NORMAL, COMFORT, ECO or AWAY
        :param type: API.OVERRIDE_TYPE. NOW, TIMER, FROM_TO or CONSTANT
        :param target_type: API.OVERRIDE_TARGET. GLOBAL or ZONE
        :param target_id: the target id (default -1)
        :param end_time: the end time (default -1), format YYYYMMDDhhmm, where mm must be in whole 15 minutes
        :param start_time: the start time (default -1), format YYYYMMDDhhmm, where mm must be in whole 15 minutes
        """
        if not mode in nobo.API.OVERRIDE_MODES:
            raise ValueError(f'Unknown override mode {mode}')
        if not type in nobo.API.OVERRIDE_TYPES:
            raise ValueError(f'Unknown override type {type}')
        if not target_type in nobo.API.OVERRIDE_TARGETS:
            raise ValueError(f'Unknown override target type {target_type}')
        if target_id != '-1' and not target_id in self.zones:
            raise ValueError(f'Unknown override target {target_id}')
        if end_time != '-1':
            if not nobo.API.is_valid_datetime(end_time):
                raise ValueError(f'Illegal end_time {end_time}: Cannot parse')
            if not nobo.API.time_is_quarter(end_time[-2:]):
                raise ValueError(f'Illegal end_time {end_time}: Must be in whole 15 minutes')
        if start_time != '-1':
            if not nobo.API.is_valid_datetime(start_time):
                raise ValueError(f'Illegal start_time: {start_time}: Cannot parse')
            if not nobo.API.time_is_quarter(end_time[-2:]):
                raise ValueError(f'Illegal start_time {end_time}: Must be in whole 15 minutes')
        command = [nobo.API.ADD_OVERRIDE, '1', mode, type, end_time, start_time, target_type, target_id]
        await self.async_send_command(command)
        for o in self.overrides: # Save override before command has finished executing
            if self.overrides[o]['target_id'] == target_id:
                self.overrides[o]['mode'] = mode
                self.overrides[o]['type'] = type

    def update_zone(self, zone_id, name=None, week_profile_id=None, temp_comfort_c=None, temp_eco_c=None, override_allowed=None):
        self._create_task(self.async_update_zone(zone_id, name, week_profile_id, temp_comfort_c, temp_eco_c, override_allowed))

    async def async_update_zone(self, zone_id, name=None, week_profile_id=None, temp_comfort_c=None, temp_eco_c=None, override_allowed=None):
        """
        Update the name, week profile, temperature or override allowing for a zone.

        :param zone_id: the zone id
        :param name: the new zone name (default None)
        :param week_profile_id: the new id for a week profile (default None)
        :param temp_comfort_c: the new comfort temperature (default None)
        :param temp_eco_c: the new eco temperature (default None)
        :param override_allowed: the new override allow setting (default None)
        """

        if not zone_id in self.zones:
            raise ValueError(f'Unknown zone id {zone_id}')

        # Initialize command with the current zone settings
        command = [nobo.API.UPDATE_ZONE] + list(self.zones[zone_id].values())

        # Replace command with arguments that are not None.
        if name:
            name = name.replace(" ", "\u00A0")
            if len(name.encode('utf-8')) > 100:
                raise ValueError(f'Zone name "{name}" too long (max 100 bytes when encoded as UTF-8)')
            command[2] = name
        if week_profile_id:
            if not week_profile_id in self.week_profiles:
                raise ValueError(f'Unknown week profile id {week_profile_id}')
            command[3] = week_profile_id
        if temp_comfort_c:
            nobo.API.validate_temperature(temp_comfort_c)
            command[4] = temp_comfort_c
            self.zones[zone_id]['temp_comfort_c'] = temp_comfort_c # Save setting before sending command
        if temp_eco_c:
            nobo.API.validate_temperature(temp_eco_c)
            command[5] = temp_eco_c
            self.zones[zone_id]['temp_eco_c'] = temp_eco_c # Save setting before sending command
        if override_allowed:
            if override_allowed != nobo.API.OVERRIDE_NOT_ALLOWED and override_allowed != nobo.API.OVERRIDE_ALLOWED:
                raise ValueError(f'Illegal value for override allowed: {override_allowed}')
            command[6] = override_allowed
        if int(command[4]) < int(command[5]):
            raise ValueError(f'Comfort temperature({command[4]}°C) cannot be less than eco temperature({command[5]}°C)')

        await self.async_send_command(command)


    async def async_add_week_profile(self, name, profile=None):
        """
        Add the name and profile parameter for a week.

        :param name: the new zone name
        :param profile: the new profile (default None)
        """

        # if no profile is defined
        if profile is None:
            profile=['00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000']
        _LOGGER.debug('profile: %s', ",".join(profile))
        nobo.API.validate_week_profile(profile)

        # profile id is decided by the hub
        week_profile_id='0'
        converted_profile =','.join(profile)
        name = name.replace(" ", "\u00A0")
        if len(name.encode('utf-8')) > 100:
            raise ValueError(f'Zone name "{name}" too long (max 100 bytes when encoded as UTF-8)')

        command = [nobo.API.ADD_WEEK_PROFILE] + [week_profile_id] + [name] + [converted_profile]

        await self.async_send_command(command)


    async def async_update_week_profile(self, week_profile_id: str, name=None, profile=None):
        """
        Update the name and profile parameter for a week.

        :param week_profile_id: the week_profile_id
        :param name: the new zone name (default None)
        :param profile: the new profile (default None)
        """

        if week_profile_id not in self.week_profiles:
            raise ValueError(f"Unknown week profile {week_profile_id}")
        if name is None and profile is None:
            raise ValueError("Set at least name or profile to update")

        if name:
            name = name.replace(" ", "\u00A0")
            if len(name.encode('utf-8')) > 100:
                 raise ValueError(f'Zone name "{name}" too long (max 100 bytes when encoded as UTF-8)')
        else:
            name = self.week_profiles[week_profile_id]["name"]

        if profile:
            nobo.API.validate_week_profile(profile)
        else:
            profile = self.week_profiles[week_profile_id]["profile"]

        command = [nobo.API.UPDATE_WEEK_PROFILE, week_profile_id, name, ','.join(profile)]
        await self.async_send_command(command)

    async def async_remove_week_profile(self, week_profile_id: str):
        """
        Remove the week profile.

        :param week_profile_id: the week_profile_id
        """

        if week_profile_id not in self.week_profiles:
            raise ValueError(f"Unknown week profile {week_profile_id}")

        if week_profile_id in (v['week_profile_id'] for k, v in self.zones.items()):
            raise ValueError(f"Week profile {week_profile_id} in use, can not remove")

        name = self.week_profiles[week_profile_id]["name"]
        profile = self.week_profiles[week_profile_id]["profile"]

        command = [nobo.API.REMOVE_WEEK_PROFILE, week_profile_id, name, ','.join(profile)]
        await self.async_send_command(command)

    def get_week_profile_status(self, week_profile_id, dt=datetime.datetime.today()):
        """
        Get the status of a week profile at a certain time in the week. Monday is day 0.

        :param week_profile_id: -- the week profile id in question
        :param dt: -- datetime for the status in question (default datetime.datetime.today())

        :return: the status for the profile
        """
        profile = self.week_profiles[week_profile_id]['profile']
        target = (dt.hour*100) + dt.minute
        # profile[0] is always 0000x, so this provides the initial status
        status = profile[0][-1]
        weekday = 0
        for timestamp in profile[1:]:
            if timestamp[:4] == '0000':
                weekday += 1
            if weekday == dt.weekday():
                if int(timestamp[:4]) <= target:
                    status = timestamp[-1]
                else:
                    break
        _LOGGER.debug('Status at %s on weekday %s is %s', target, dt.weekday(), nobo.API.DICT_WEEK_PROFILE_STATUS_TO_NAME[status])
        return nobo.API.DICT_WEEK_PROFILE_STATUS_TO_NAME[status]

    def get_zone_override_mode(self, zone_id):
        """
        Get the override mode of a zone.

        :param zone_id: the zone id in question

        :return: the override mode for the zone
        """
        mode = nobo.API.NAME_NORMAL
        for o in self.overrides:
            if self.overrides[o]['mode'] == '0':
                continue # "normal" overrides
            elif (self.overrides[o]['target_type'] == nobo.API.OVERRIDE_TARGET_ZONE
                  and self.overrides[o]['target_id'] == zone_id):
                mode = nobo.API.DICT_OVERRIDE_MODE_TO_NAME[self.overrides[o]['mode']]
                # Takes precedence over global override
                break
            elif (self.zones[zone_id]['override_allowed'] == '1'
                  and self.overrides[o]['target_type'] == nobo.API.OVERRIDE_TARGET_GLOBAL):
                mode = nobo.API.DICT_OVERRIDE_MODE_TO_NAME[self.overrides[o]['mode']]

        _LOGGER.debug('Current override for zone %s is %s', self.zones[zone_id]['name'], mode)
        return mode

    def get_current_zone_mode(self, zone_id, now=None):
        """
        Get the mode of a zone at a certain time. If the zone is overridden only now is possible.

        :param zone_id: the zone id in question
        :param now: datetime for the status in question (default datetime.datetime.today())

        :return: the mode for the zone
        """
        if now is None:
            now = datetime.datetime.today()
        current_time = (now.hour*100) + now.minute
        current_mode = self.get_zone_override_mode(zone_id)
        if current_mode == nobo.API.NAME_NORMAL:
            # no override - find mode from week profile
            current_mode = self.get_week_profile_status(self.zones[zone_id]['week_profile_id'], now)

        _LOGGER.debug('Current mode for zone %s at %s is %s', self.zones[zone_id]['name'], current_time, current_mode)
        return current_mode

    def get_current_component_temperature(self, serial):
        """
        Get the current temperature from a component.

        :param serial: the serial for the component in question

        :return: the temperature for the component (default N/A)
        """
        current_temperature = None

        if serial in self.temperatures:
            current_temperature = self.temperatures[serial]
            if current_temperature == 'N/A':
                current_temperature = None

        if current_temperature:
            _LOGGER.debug('Current temperature for component %s is %s', self.components[serial]['name'], current_temperature)
        return current_temperature

    # Function to get (first) temperature in a zone
    def get_current_zone_temperature(self, zone_id):
        """
        Get the current temperature from (the first component in) a zone.

        :param zone_id: the id for the zone in question

        :return: the temperature for the (first) component in the zone (default N/A)
        """
        current_temperature = None

        for c in self.components:
            if self.components[c]['zone_id'] == zone_id:
                current_temperature = self.get_current_component_temperature(c)
                if current_temperature != None:
                    break

        if current_temperature:
            _LOGGER.debug('Current temperature for zone %s is %s', self.zones[zone_id]['name'], current_temperature)
        return current_temperature
