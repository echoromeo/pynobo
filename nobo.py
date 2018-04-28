#!/usr/bin/python3

# Python Websocet Control of Nobø Hub - Nobø Energy Control
# This system/service/software is not officially supported or endorsed by Glen Dimplex Nordic AS, and I am not an official partner of Glen Dimplex Nordic AS
# API: https://www.glendimplex.no/media/15650/nobo-hub-api-v-1-1-integration-for-advanced-users.pdf

# Call using the three last digits in the hub serial, or full serial and IP if you do not want to discover on UDP
# Example: glen = nobo('123') or glen = nobo('123123123123', '10.0.0.128', False)

import time
import datetime
import warnings
import logging
import collections
import socket
import threading

class nobo:

    # All the commands and responses from API v1.1 - Some with sensible names, others not yet given better names
    class API:
        VERSION = '1.1'

        START = 'HELLO'			    #HELLO <version of command set> <Hub s.no.> <date and time in format 'yyyyMMddHHmmss'>
        REJECT = 'REJECT'			#REJECT <reject code>
        HANDSHAKE = 'HANDSHAKE'	    #HANDSHAKE

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
        RESPONSE_HUB_INFO = 'H05'           # G00 request complete signal + static info: H05 <Snr> <Name> <DefaultAwayOverrideLength> <ActiveOverrideid> <SoftwareVersion> <HardwareVersion> <Producti???

        EXECUTE_START_SEARCH = 'X00'
        EXECUTE_STOP_SEARCH = 'X01'
        EXECUTE_COMPONENT_PAIR = 'X03'
        RESPONSE_STARTED_SEARCH = 'Y00'
        RESPONSE_STOPPED_SEARCH = 'Y01'
        RESPONSE_COMPONENT_TEMP = 'Y02'     # Component temperature value sent as part ora GOO response, or pushed from the Hub a utomaticall y to all connected clients whenever the Hub has received updated temperature data.
        RESPONSE_COMPONENT_PAIR = 'Y03'
        RESPONSE_COMPONENT_FOUND = 'Y04'

        RESPONSE_ERROR = 'E00'              # Other error messages than E00 may also be sent from the Hub (E01, E02 etc.): E00 <command> <message>

        OVERRIDE_MODE_NORMAL = '0'
        OVERRIDE_MODE_COMFORT = '1'
        OVERRIDE_MODE_ECO = '2'
        OVERRIDE_MODE_AWAY = '3'

        OVERRIDE_TYPE_NOW = '0'
        OVERRIDE_TYPE_TIMER = '1'
        OVERRIDE_TYPE_FROM_TO = '2'
        OVERRIDE_TYPE_CONSTANT = '3'

        OVERRIDE_TARGET_GLOBAL = '0'
        OVERRIDE_TARGET_ZONE = '1'
        OVERRIDE_TARGET_COMPONENT = '2'     # Not implemented yet

        OVERRIDE_ID_NONE = '-1'
        OVERRIDE_ID_HUB = '-1'

        WEEK_PROFILE_STATE_ECO = '0'
        WEEK_PROFILE_STATE_COMFORT = '1'
        WEEK_PROFILE_STATE_AWAY = '2'
        WEEK_PROFILE_STATE_OFF = '4'

        STRUCT_KEYS_HUB = ['serial', 'name', 'default_away_override_length', 'override_id', 'software_version', 'hardware_version', 'production_date']
        STRUCT_KEYS_ZONE = ['zone_id', 'name', 'week_profile_id', 'temp_comfort_c', 'temp_eco_c', 'override_allowed']
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

    def __init__(self, serial, ip=None, discover=True):
        self.logger = logging.getLogger(__name__)
        self.hub_info = {}
        self.zones = collections.OrderedDict()
        self.components = collections.OrderedDict()
        self.week_profiles = collections.OrderedDict()
        self.overrides = collections.OrderedDict()
        self.temperatures = collections.OrderedDict()

        # Get a socket connection, either by scanning or directly
        if discover:
            discovered_hubs = self.discover_hubs(serial=serial, ip=ip)
            if not discovered_hubs:
                self.logger.error("Failed to discover any Nobø Ecohubs")
                raise Exception("Failed to discover any Nobø Ecohubs")
            while discovered_hubs:
                (discover_ip, discover_serial) = discovered_hubs.pop()
                try:
                    self.connect_hub(discover_ip, discover_serial)
                    break  # We connect to the first valid hub, no reason to try the rest
                except Exception as e:
                    # This might not have been the Ecohub we wanted (wrong serial)
                    self.logger.warning("Could not connect to {}:{} - {}".format(
                                        discover_ip, discover_serial, e))
        else:
            # check if we have an IP
            if not ip:
                self.logger.error('Could not connect, no ip address provided')
                raise ValueError('Could not connect, no ip address provided')

            # check if we have a valid serial before we start connection
            if len(serial) != 12:
                self.logger.error('Could not connect, no valid serial number provided')
                raise ValueError('Could not connect, no valid serial number provided')

            self.connect_hub(ip, serial)

        if not self.client:
            self.logger.error("Failed to connect to Ecohub")
            raise Exception("Failed to connect to Ecohub")

        # start thread for continously receiving new data from hub
        self.socket_receive_thread = threading.Thread(target=self.socket_receive, daemon=True)
        self.socket_receive_exit_flag = threading.Event()
        self.socket_received_all_info = threading.Event()
        self.socket_connected = threading.Event()
        self.socket_connected.set()
        self.socket_receive_thread.start()

        # Fetch all info
        self.send_command([self.API.GET_ALL_INFO])
        self.socket_received_all_info.wait()

        self.logger.info('connected to Nobø Hub')


    def connect_hub(self, ip, serial):
        """Attempt initial connection and handshake

        Keyword arguments:
        ip -- The ecohub ip address to connect to
        serial -- The complete 12 digit serial number of the hub to connect to
        """
        # create an ipv4 (AF_INET) socket object using the tcp protocol (SOCK_STREAM)
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.settimeout(5)

        # connect the client - let a timeout exception be raised?
        self.client.connect((ip, 27779))

        # start handshake: "HELLO <version of command set> <Hub s.no.> <date and time in format 'yyyyMMddHHmmss'>\r"
        self.send_command([self.API.START, self.API.VERSION, serial, time.strftime('%Y%m%d%H%M%S')])

        # receive the response data (4096 is recommended buffer size)
        response = self.get_response()
        self.logger.debug('first handshake response: %s', response)

        # successful response is "HELLO <its version of command set>\r"
        if response[0][0] == self.API.START:
            # send “REJECT\r” if command set is not supported? No need to abort if Hub is ok with the mismatch?
            if response[0][1] != self.API.VERSION:
                #self.send_command([self.API.REJECT])
                self.logger.warning('api version might not match, hub: v{}, pynobo: v{}'.format(response[0][1], self.API.VERSION))
                warnings.warn('api version might not match, hub: v{}, pynobo: v{}'.format(response[0][1], self.API.VERSION)) #overkill?

            # send/receive handshake complete
            self.send_command([self.API.HANDSHAKE])
            self.last_handshake = time.time()
            response = self.get_response()
            self.logger.debug('second handshake response: %s', response)

            if response[0][0] == self.API.HANDSHAKE:
                # Connect OK, store connection information for later reconnects
                self.hub_ip = ip
                self.hub_serial = serial
                return
            else:
                # Something went wrong...
                self.logger.error("Final handshake not as expected %s", response[0][0])
                self.client.close()
                self.client = None
                raise Exception("Final handshake not as expected {}".format(response[0][0]))
        else:
            # Reject response: "REJECT <reject code>\r"
            # 0=client command set version too old (or too new!).
            # 1=Hub serial number mismatch.
            # 2=Wrong number of arguments.
            # 3=Timestamp incorrectly formatted
            self.logger.error('connection to hub rejected: {}'.format(response[0]))
            self.client.close()
            self.client = None
            raise Exception('connection to hub rejected: {}'.format(response[0]))

    def reconnect_hub(self):
        # close socket properly so connect_hub can restart properly
        if self.client:
            self.client.close()
            self.client = None

        # attempt reconnect to the lost hub
        rediscovered_hub = None
        while not rediscovered_hub:
            self.logger.debug('hub not rediscovered')
            rediscovered_hub = self.discover_hubs(serial=self.hub_serial, ip=self.hub_ip)
            time.sleep(10)
        self.connect_hub(self.hub_ip, self.hub_serial)
        self.socket_connected.set()
        self.logger.info('reconnected to Nobø Hub')

        # Update all info
        self.send_command([self.API.GET_ALL_INFO])

    def discover_hubs(self, serial, ip=None, autodiscover_wait=3.0):
        """Attempts to autodiscover Nobø Ecohubs on the local networkself.

        Every two seconds, the Hub sends one UDP broadcast packet on port 10000
        to broadcast IP 255.255.255.255, we listen for this package, and collect
        every packet that contains the magic __NOBOHUB__ identifier. The set
        of (ip, serial) tuples is returned

        Specifying a complete 12 digit serial number or an ip address, will only
        attempt to discover hubs matching that serial, ip address or both.

        Keyword arguments:
        serial -- The last 3 digits of the Ecohub serial number or the complete
                  12 digit serial number
        ip -- ip address to search for Ecohub at (default None)
        autodiscover_wait -- how long to wait for an autodiscover package from
                             the hub (default 3.0)
        """
        discovered_hubs = set()

        ds = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ds.settimeout(0.1)
        ds.bind((' ',10000))

        start_time = time.time()
        while (start_time + autodiscover_wait > time.time()):
            try:
                broadcast = ds.recvfrom(1024)
            except socket.timeout:
                broadcast = ""
            else:
                self.logger.info('broadcast received: %s', broadcast)
                # Expected string “__NOBOHUB__123123123”, where 123123123 is replaced with the first 9 digits of the Hub’s serial number.
                if broadcast[0][:11] == b'__NOBOHUB__':
                    discover_serial = str(broadcast[0][-9:], 'utf-8')
                    discover_ip = broadcast[1][0]
                    if len(serial) == 12:
                        if discover_serial != serial[0:9]:
                            # This is not the Ecohub you are looking for
                            discover_serial = None
                    else:
                        discover_serial += serial
                    if ip and discover_ip != ip:
                        # This is not the Ecohub you are looking for
                        discover_ip = None
                    if discover_ip and discover_serial:
                        discovered_hubs.add( (discover_ip, discover_serial) )

        ds.close()
        return discovered_hubs

    # Function to send a list with command string(s)
    def send_command(self, command_array):
        self.logger.debug('sending: %s', command_array)

        # Convert integers to string
        for idx, c in enumerate(command_array):
            if isinstance(c, int):
                command_array[idx] = str(c)

        message = ' '.join(command_array).encode('utf-8')
        try:
            self.client.send(message + b'\r')
        except ConnectionResetError:
            self.logger.info('lost connection to hub')
            self.socket_connected.clear()

    # Function to receive a string from the hub and reformat string list
    def get_response(self, keep_alive=False, bufsize=4096):
        response = b''
        while response[-1:] != b'\r':
            try:
                response += self.client.recv(bufsize)
            except socket.timeout:
                # handshake needs to be sent every < 30 sec, preferably every 14 seconds
                if keep_alive:
                    now = time.time()
                    if now - self.last_handshake > 14:
                        self.send_command([self.API.HANDSHAKE])
                        self.last_handshake = now
                else:
                    break
            except ConnectionResetError:
                self.logger.info('lost connection to hub')
                self.socket_connected.clear()
                break

        # Handle more than one response in one receive
        response_list = str(response, 'utf-8').split('\r')
        response = []
        for r in response_list:
            if r:
                response.append(r.split(' '))

        return response

    # Task running in daemon thread
    def socket_receive(self):
        while not self.socket_receive_exit_flag.is_set():
            if self.socket_connected.is_set():
                resp = self.get_response(True)
                for r in resp:
                    self.logger.debug('received: %s', r)

                    if r[0] == self.API.HANDSHAKE:
                        pass # Handshake, no action needed

                    elif r[0][0] == 'E':
                        self.logger.error('error! what did you do? %s', r)
                        #TODO: Raise something here?

                    else:
                        self.response_handler(r)

            else:
                self.reconnect_hub()

        self.logger.info('receive thread exited')

    def response_handler(self, r):
        # All info incoming, clear existing info
        if r[0] == self.API.RESPONSE_SENDING_ALL_INFO:
            self.socket_received_all_info.clear()
            self.hub_info = {}
            self.zones = {}
            self.components = {}
            self.week_profiles = {}
            self.overrides = {}

        # The added/updated info messages
        elif r[0] in [self.API.RESPONSE_ZONE_INFO, self.API.RESPONSE_ADD_ZONE ,self.API.RESPONSE_UPDATE_ZONE]:
            dicti = collections.OrderedDict(zip(self.API.STRUCT_KEYS_ZONE, r[1:-1]))
            self.zones[dicti['zone_id']] = dicti
            self.logger.info('added/updated zone: %s', dicti['name'])

        elif r[0] in [self.API.RESPONSE_COMPONENT_INFO, self.API.RESPONSE_ADD_COMPONENT ,self.API.RESPONSE_UPDATE_COMPONENT]:
            dicti = collections.OrderedDict(zip(self.API.STRUCT_KEYS_COMPONENT, r[1:]))
            self.components[dicti['serial']] = dicti
            self.logger.info('added/updated component: %s', dicti['name'])

        elif r[0] in [self.API.RESPONSE_WEEK_PROFILE_INFO, self.API.RESPONSE_ADD_WEEK_PROFILE, self.API.RESPONSE_UPDATE_WEEK_PROFILE]:
            dicti = collections.OrderedDict(zip(self.API.STRUCT_KEYS_WEEK_PROFILE, r[1:]))
            dicti['profile'] = r[-1].split(',')
            self.week_profiles[dicti['week_profile_id']] = dicti
            self.logger.info('added/updated week profile: %s', dicti['name'])

        elif r[0] in [self.API.RESPONSE_OVERRIDE_INFO, self.API.RESPONSE_ADD_OVERRIDE]:
            dicti = collections.OrderedDict(zip(self.API.STRUCT_KEYS_OVERRIDE, r[1:]))
            self.overrides[dicti['override_id']] = dicti
            self.logger.info('added/updated override: id %s', dicti['override_id'])

        elif r[0] in [self.API.RESPONSE_HUB_INFO, self.API.RESPONSE_UPDATE_HUB_INFO]:
            self.hub_info = collections.OrderedDict(zip(self.API.STRUCT_KEYS_HUB, r[1:]))
            self.logger.info('updated hub info: %s', self.hub_info)
            if r[0] == self.API.RESPONSE_HUB_INFO:
                self.socket_received_all_info.set()

        # The removed info messages
        elif r[0] == self.API.RESPONSE_REMOVE_ZONE:
            dicti = collections.OrderedDict(zip(self.API.STRUCT_KEYS_ZONE, r[1:-1]))
            popped_zone = self.zones.pop(dicti['zone_id'], None)
            self.logger.info('removed zone: %s', dicti['name'])

        elif r[0] == self.API.RESPONSE_REMOVE_COMPONENT:
            dicti = collections.OrderedDict(zip(self.API.STRUCT_KEYS_COMPONENT, r[1:]))
            popped_component = self.components.pop(dicti['serial'], None)
            self.logger.info('removed component: %s', dicti['name'])

        elif r[0] == self.API.RESPONSE_REMOVE_WEEK_PROFILE:
            dicti = collections.OrderedDict(zip(self.API.STRUCT_KEYS_WEEK_PROFILE, r[1:]))
            popped_profile = self.week_profiles.pop(dicti['week_profile_id'], None)
            self.logger.info('removed week profile: %s', dicti['name'])

        elif r[0] == self.API.RESPONSE_REMOVE_OVERRIDE:
            dicti = collections.OrderedDict(zip(self.API.STRUCT_KEYS_OVERRIDE, r[1:]))
            popped_override = self.overrides.pop(dicti['override_id'], None)
            self.logger.info('removed override: id%s', dicti['override_id'])

        # Component temperature data
        elif r[0] == self.API.RESPONSE_COMPONENT_TEMP:
            self.temperatures[r[1]] = r[2]
            self.logger.info('updated temperature from {}: {}'.format(r[1], r[2]))

        # Internet settings
        elif r[0] == self.API.RESPONSE_UPDATE_INTERNET_ACCESS:
            internet_access = r[1]
            encryption_key = 0
            for i in range(2, 18):
                encryption_key = (encryption_key << 8) + int(r[i])
            self.logger.debug('internet enabled: {}, key: {}'.format(internet_access, hex(encryption_key)))

        else:
            self.logger.warning('behavior undefined for this response: {}'.format(r))
            warnings.warn('behavior undefined for this response: {}'.format(r)) #overkill?

    # Function to override hub/zones/components. "Override" to mode 0 to disable an existing override
    def create_override(self, mode, type, target_type, target_id='-1', end_time='-1', start_time='-1'):
        command = [self.API.ADD_OVERRIDE, '1', mode, type, end_time, start_time, target_type, target_id]
        self.send_command(command)
    
    # Function to update name, week profile, temperature or override allowing for a zone
    def update_zone(self, zone_id, name=None, week_profile_id=None, temp_comfort_c=None, temp_eco_c=None, override_allowed=None):
        # Initialize command with the current zone settings
        command = [self.API.UPDATE_ZONE] + list(self.zones[zone_id].values()) + [self.API.OVERRIDE_ID_NONE]
        
        # Replace command with arguments that are not None. Is there a more elegant way?
        if name:
            command[2] = name
        if week_profile_id:
            command[3] = week_profile_id
        if temp_comfort_c:
            command[4] = temp_comfort_c
        if temp_eco_c:
            command[5] = temp_eco_c
        if override_allowed:
            command[6] = override_allowed

        self.send_command(command)

    # Function to find the status of a profile at a certain time in the week. Monday is day 0
    def get_week_profile_status(self, profile, dt):
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
        self.logger.debug('Status at {} on weekday {} is {}'.format(dt.weekday(), target, status))
        return status

	# Function to find mode in a zone right now
    def get_current_zone_mode(self, zone_id, now=datetime.datetime.today()):
        current_time = (now.hour*100) + now.minute
        current_mode = ''
        
        if self.zones[zone_id]['override_allowed'] == '1':
            for o in self.overrides:
                if self.overrides[o]['mode'] == '0':
                    continue # "normal" overrides
                elif self.overrides[o]['target_type'] == self.API.OVERRIDE_TARGET_ZONE:
                    if self.overrides[o]['target_id'] == zone_id:
                        current_mode = self.API.DICT_OVERRIDE_MODE_TO_NAME[self.overrides[o]['mode']]
                        break
                elif self.overrides[o]['target_type'] == self.API.OVERRIDE_TARGET_GLOBAL:
                    current_mode = self.API.DICT_OVERRIDE_MODE_TO_NAME[self.overrides[o]['mode']]

        # no override - figure out from week profile
        if not current_mode:
            current_profile = self.week_profiles[self.zones[zone_id]['week_profile_id']]['profile']
            current_status = self.get_week_profile_status(current_profile, now)
            current_mode = self.API.DICT_WEEK_PROFILE_STATUS_TO_NAME[current_status]

        self.logger.debug('Current mode for zone {} at {} is {}'.format(self.zones[zone_id]['name'], current_time, current_mode))
        return current_mode
