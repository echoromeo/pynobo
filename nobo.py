#!/usr/bin/python3

# Python Websocet Control of Nobø Hub - Nobø Energy Control
# This system/service/software is not officially supported or endorsed by Glen Dimplex Nordic AS, and I am not an official partner of Glen Dimplex Nordic AS
# API: https://www.glendimplex.no/media/15650/nobo-hub-api-v-1-1-integration-for-advanced-users.pdf

# Call using the three last digits in the hub serial, or full serial and IP if you do not want to discover on UDP
# Example: glen = nobo('123') or glen = nobo('123123123123', '10.0.0.128', False)

import time
import arrow
import warnings
import logging
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
        RESPONSE_ADD_B00 = 'B00'
        RESPONSE_ADD_B01 = 'B01'
        RESPONSE_ADD_B02 = 'B02'
        RESPONSE_ADD_B03 = 'B03'

        UPDATE_ZONE = 'U00'             # Updates Zone to hub database: U00 <Zone id> <Name> <Active week profile id> <Comfort temperature> <Eco temperature> <Allow overrides> <Active override id>
        UPDATE_COMPONENT = 'U01'        # Updates Component to hub database: U01 <Serial number> <Status> <Name> <Reverse on/off?> <Zoneld> <Active override Id> <Temperature sensor for zone>
        UPDATE_WEEK_PROFILE = 'U02'     # Updates Week Profile to hub database: U02 <Week profile id> <Name> <Profile>
        UPDATE_HUB_INFO = 'U03'         # Updates hub information: U83 <Snr> <Name> <DefaultAwayOverrideLength> <ActiveOverrideid> <Softwareversion> <Hardwareversion> <Producti????
        UPDATE_INTERNET_ACCESS = 'U06'  # Updates hub internet connectivity function and encryption key (LAN only): U86 <Enable internet access> <Encryption key> <Reserved 1> <Reserved 2>
        RESPONSE_UPDATE_V00 = 'V00'
        RESPONSE_UPDATE_V01 = 'V01'
        RESPONSE_UPDATE_V02 = 'V02'
        RESPONSE_UPDATE_V03 = 'V03'
        RESPONSE_UPDATE_V06 = 'V06'

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

        RESPONSE_REMOVE_S00 = 'S00'
        RESPONSE_REMOVE_S01 = 'S01'
        RESPONSE_REMOVE_S02 = 'S02'
        RESPONSE_REMOVE_S03 = 'S03'

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
        RESPONSE_STATIC_INFO = 'H05'        # G00 request complete signal + static info: H05 <Snr> <Name> <DefaultAwayOverrideLength> <ActiveOverrideid> <SoftwareVersion> <HardwareVersion> <Producti???

        EXECUTE_START_SEARCH = 'X00'
        EXECUTE_STOP_SEARCH = 'X01'
        EXECUTE_COMPONENT_PAIR = 'X03'
        RESPONSE_STARTED_SEARCH = 'Y00'
        RESPONSE_STOPPED_SEARCH = 'Y01'
        RESPONSE_COMPONENT_TEMP = 'Y02'     # Component temperature value sent as part ora GOO response, or pushed from the Hub a utomaticall y to all connected clients whenever the Hub has received updated temperature data.
        RESPONSE_COMPONENT_PAIR = 'Y03'
        RESPONSE_COMPONENT_FOUND = 'Y04'

        RESPONSE_ERROR = 'E00'              # Other error messages than E00 may also be sent from the Hub (E01, E02 etc.): E00 <command> <message>

        OVERRIDE_MODE_OFF = '0'
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

        STRUCT_KEYS_HUB = ['serial', 'name', 'default_away_override_length', 'override_id', 'software_version', 'hardware_version', 'production_date']
        STRUCT_KEYS_ZONE = ['zone_id', 'name', 'week_profile_id', 'temp_comfort_c', 'temp_eco_c', 'override_allowed', 'override_id']
        STRUCT_KEYS_COMPONENT = ['serial', 'status', 'name', 'reverse_onoff', 'zone_id', 'override_id', 'tempsensor_for_zone_id']
        STRUCT_KEYS_WEEK_PROFILE = ['week_profile_id', 'name', 'profile'] # profile is minimum 7 and probably more values separated by comma
        STRUCT_KEYS_OVERRIDE = ['override_id', 'mode', 'type', 'end_time', 'start_time', 'target_type', 'target_id']

    def __init__(self, serial, ip=None, discover=True):
        self.hub_info = {}
        self.zones = {}
        self.components = {}
        self.week_profiles = {}
        self.overrides = {}

        # Get a socket connection, either by scanning or directly
        if discover:
            discovered_hubs = self.discover_hubs(serial=serial, ip=ip)
            if not discovered_hubs:
                logging.error("Failed to discover any Nobø Ecohubs")
                raise Exception("Failed to discover any Nobø Ecohubs")
            while discovered_hubs:
                (discover_ip, discover_serial) = discovered_hubs.pop()
                try:
                    self.connect_hub(discover_ip, discover_serial)
                    break  # We connect to the first valid hub, no reason to try the rest
                except Exception as e:
                    # This might not have been the Ecohub we wanted (wrong serial)
                    logging.warning("Could not connect to {}:{} - {}".format(
                                    discover_ip, discover_serial, e))
        else:
            # check if we have an IP
            if not ip:
                logging.error('Could not connect, no ip address provided')
                raise ValueError('Could not connect, no ip address provided')

            # check if we have a valid serial before we start connection
            if len(serial) != 12:
                logging.error('Could not connect, no valid serial number provided')
                raise ValueError('Could not connect, no valid serial number provided')

            self.connect_hub(ip, serial)

        if not self.client:
            logging.error("Failed to connect to Ecohub")
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

        logging.info('connected to Nobø Hub')


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
        self.send_command([self.API.START, self.API.VERSION, serial, arrow.now().format('YYYYMMDDHHmmss')])

        # receive the response data (4096 is recommended buffer size)
        response = self.get_response()
        logging.debug('first handshake response: %s', response)

        # successful response is "HELLO <its version of command set>\r"
        if response[0][0] == self.API.START:
            # send “REJECT\r” if command set is not supported? No need to abort if Hub is ok with the mismatch?
            if response[0][1] != self.API.VERSION:
                #self.send_command([self.API.REJECT])
                logging.warning('api version might not match, hub: v{}, pynobo: v{}'.format(response[0][1], self.API.VERSION))
                warnings.warn('api version might not match, hub: v{}, pynobo: v{}'.format(response[0][1], self.API.VERSION)) #overkill?

            # send/receive handshake complete
            self.send_command([self.API.HANDSHAKE])
            self.last_handshake = time.time()
            response = self.get_response()
            logging.debug('second handshake response: %s', response)

            if response[0][0] == self.API.HANDSHAKE:
                # Connect OK, store connection information for later reconnects
                self.hub_ip = ip
                self.hub_serial = serial
                return
            else:
                # Something went wrong...
                logging.error("Final handshake not as expected %s", response[0][0])
                self.client.close()
                self.client = None
                raise Exception("Final handshake not as expected {}".format(response[0][0]))
        else:
            # Reject response: "REJECT <reject code>\r"
            # 0=client command set version too old (or too new!).
            # 1=Hub serial number mismatch.
            # 2=Wrong number of arguments.
            # 3=Timestamp incorrectly formatted
            logging.error('connection to hub rejected: {}'.format(response[0]))
            self.client.close()
            self.client = None
            raise Exception('connection to hub rejected: {}'.format(response[0]))

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
                logging.info('broadcast received: %s', broadcast)
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
        logging.debug('sending: %s', command_array)
        message = ' '.join(command_array).encode('utf-8')
        try:
            self.client.send(message + b'\r')
        except ConnectionResetError:
            logging.info('lost connection to hub')
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
                logging.info('lost connection to hub')
                self.socket_connected.clear()
                break

        # Handle more than one response in one receive
        response_list = str(response, 'utf-8').split('\r')
        response = []
        for r in response_list:
            if r:
                response.append(r.split(' '))

        return response

    # Function to override hub/zones/components. "Override" to mode 0 to disable an existing override?
    def create_override(self, mode, type, target_type, target_id='-1', end_time='-1', start_time='-1'):
        command = [self.API.ADD_OVERRIDE, '1', mode, type, end_time, start_time, target_type, target_id]
        self.send_command(command)

    # Task running in daemon thread
    def socket_receive(self):
        while not self.socket_receive_exit_flag.is_set():
            if self.socket_connected.is_set():
                resp = self.get_response(True)
                for r in resp:
                    logging.debug('received: %s', r)

                    if r[0] in [self.API.HANDSHAKE]:
                        pass # Handshake, no action needed

                    # A lot of info is incoming, will end with RESPONSE_STATIC_INFO
                    elif r[0] == self.API.RESPONSE_SENDING_ALL_INFO:
                        self.socket_received_all_info.clear()

                    # The added/updated info messages 
                    elif r[0] in [self.API.RESPONSE_ZONE_INFO, self.API.RESPONSE_UPDATE_V00]:
                        dicti = dict(zip(self.API.STRUCT_KEYS_ZONE, r[1:]))
                        self.zones[dicti['zone_id']] = dicti
                        logging.info('added/updated zone: %s', dicti['name'])

                    elif r[0] in [self.API.RESPONSE_COMPONENT_INFO, self.API.RESPONSE_UPDATE_V01]:
                        dicti = dict(zip(self.API.STRUCT_KEYS_COMPONENT, r[1:]))
                        self.components[dicti['serial']] = dicti
                        logging.info('added/updated component: %s', dicti['name'])

                    elif r[0] in [self.API.RESPONSE_WEEK_PROFILE_INFO, self.API.RESPONSE_UPDATE_V02]:
                        dicti = dict(zip(self.API.STRUCT_KEYS_WEEK_PROFILE, r[1:]))
                        dicti['profile'] = r[-1].split(',')
                        self.week_profiles[dicti['week_profile_id']] = dicti
                        logging.info('added/updated week profile: %s', dicti['name'])

                    elif r[0] in [self.API.RESPONSE_OVERRIDE_INFO, self.API.RESPONSE_ADD_B03]:
                        dicti = dict(zip(self.API.STRUCT_KEYS_OVERRIDE, r[1:]))
                        self.overrides[dicti['override_id']] = dicti
                        logging.info('added/updated override: id %s', dicti['override_id'])

                    elif r[0] in [self.API.RESPONSE_STATIC_INFO, self.API.RESPONSE_UPDATE_V03]:
                        self.hub_info = dict(zip(self.API.STRUCT_KEYS_HUB, r[1:]))
                        logging.info('updated hub info: %s', self.hub_info)
                        if r[0] == self.API.RESPONSE_STATIC_INFO:
                            self.socket_received_all_info.set()

                    #TODO: Add all the other response_remove commands
                    elif r[0] == self.API.RESPONSE_REMOVE_S03:
                        dicti = dict(zip(self.API.STRUCT_KEYS_OVERRIDE, r[1:]))
                        popped_override = self.overrides.pop(dicti['override_id'], None)
                        logging.info('removed override: id%s', dicti['override_id'])

                    elif r[0][0] == 'E':
                        logging.error('error! what did you do? %s', r)
                        #TODO: Raise something here?

                    else:
                        logging.warning('behavior undefined for this command: {}'.format(r))
                        warnings.warn('behavior undefined for this command: {}'.format(r)) #overkill?        
            else:
                # close socket properly so connect_hub can restart properly
                self.client.close()
                self.client = None

                # attempt reconnect to the lost hub
                rediscovered_hub = None
                while not rediscovered_hub:
                    logging.debug('hub not rediscovered')
                    rediscovered_hub = self.discover_hubs(serial=self.hub_serial, ip=self.hub_ip)
                    time.sleep(10)
                self.connect_hub(self.hub_ip, self.hub_serial)
                self.socket_connected.set()
                logging.info('reconnected to Nobø Hub')

                # Fetch all info
                self.send_command([self.API.GET_ALL_INFO])

        logging.info('receive thread exited')
