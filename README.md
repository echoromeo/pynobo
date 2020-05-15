# Nobø Hub / Nobø Energy Control Websocket Interface

This system/service/software is not officially supported or endorsed by Glen Dimplex Nordic AS, and the authors/maintainer(s) are not official partner of Glen Dimplex Nordic AS

[The API (v1.1) for Nobø Hub can be found here][api]

[api]: https://www.glendimplex.no/media/15650/nobo-hub-api-v-1-1-integration-for-advanced-users.pdf

## Quick Start

    from pynobo import nobo

Either call using the three last digits in the hub serial
    
    glen = nobo('123') 

or full serial and IP if you do not want to discover on UDP:

    glen = nobo('123123123123', '10.0.0.128', False)

after that you can start playing around using the different dictionaries that should be loaded with whatever the hub gave you:

    glen.hub_info
    glen.zones
    glen.components
    glen.week_profiles
    glen.overrides
    glen.temperatures

## Available functionality


* nobo class - When called it will initialize logger and dictionaries, connect to hub and start daemon thread

* nobo.API class - All the commands and responses from API v1.1, Some with sensible names, others not yet given better names 


### Background Functions

These functions run in the background after initialization of the nobo class

* connect_hub - Attempt initial connection and handshake
* discover_hubs - Attempts to autodiscover Nobø Ecohubs on the local networkself
* reconnect_hub - Attempt to disconnect/close the connection and reconnect
 
* socket_receive - The task running in daemon thread for receiving and handling responses from the hub
* get_response - Get a response string from the hub and reformat string list before returning it
* response_handler - Handle the response(s) from the hub and updated the dictionaries accordingly

### Command Functions

These functions sends commands to the hub

* send_command - Send a list of command string(s) to the hub
* create_override - Override hub/zones/components
* update_zone - Update the name, week profile, temperature or override allowing for a zone.  

### Dictionary helper functions

These functions simplifies getting the data you want from the dictionaries

* get_week_profile_status - Get the status of a week profile at a certain time in the week 
* get_current_zone_mode - Get the mode of a zone at a certain time
* get_current_component_temperature - Get the current temperature from a component
* get_current_zone_temperature - Get the current temperature from (the first component in) a zone
