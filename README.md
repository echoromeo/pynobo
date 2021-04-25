# Nobø Hub / Nobø Energy Control TCP/IP Interface

This system/service/software is not officially supported or endorsed by Glen Dimplex Nordic AS, and the authors/maintainer(s) are not official partner of Glen Dimplex Nordic AS

[The API (v1.1) for Nobø Hub can be found here][api]

[api]: https://www.glendimplex.no/media/15650/nobo-hub-api-v-1-1-integration-for-advanced-users.pdf

## Quick Start

    import asyncio
    from pynobo import nobo

    async def main():
        # Either call using the three last digits in the hub serial
        hub = nobo('123', loop=asyncio.get_event_loop()) 
        # or full serial and IP if you do not want to discover on UDP:
        hub = nobo('123123123123', '10.0.0.128', False, loop=asyncio.get_event_loop())

        # Connect to the hub
        await hub.start()

        # Inspect what you get
        def update(hub):
            print(hub.hub_info)
            print(hub.zones)
            print(hub.components)
            print(hub.week_profiles)
            print(hub.overrides)
            print(hub.temperatures)
    
        # Listen for data updates - register before getting initial data to avoid race condition
        hub.register_callback(callback=update)

        # Get initial data
        update(hub)
    
        # Hang around and wait for data updates
        await asyncio.sleep(60)
    
        # Stop the connection
        await hub.stop()

    asyncio.run(main())

## Available functionality

* `nobo` class - When called it will initialize logger and dictionaries, connect to hub and start daemon thread.
* `nobo.API` class - All the commands and responses from API v1.1, Some with sensible names, others not yet given better names.
* `nobo.DiscoveryProtocol` - An `asyncio.DatagramProtocol` used to discover Nobø Ecohubs on the local network.

### Background Tasks

Calling `start()` will first try to discover the Nobø Ecohub on the local network, unless `discover` is set to `False`,
which required IP address and full serial (12 digits).  If an IP address is provided, or the hub is discovered, it
will attempt to connect to it, and if successful, start  the following tasks:

* keep_alive - Send a periodic keep alive message to the hub
* socket_receive - Handle incoming messages from the hub

If the connection is lost, it will attempt to reconnect.

### Command Functions

These functions sends commands to the hub.

* async_send_command - Send a list of command string(s) to the hub
* async_create_override - Override hub/zones/components
* async_update_zone - Update the name, week profile, temperature or override allowing for a zone.  

### Dictionary helper functions

These functions simplifies getting the data you want from the dictionaries. They do
not perform any I/O, and can safely be called from the event loop.

* get_week_profile_status - Get the status of a week profile at a certain time in the week 
* get_current_zone_mode - Get the mode of a zone at a certain time
* get_current_component_temperature - Get the current temperature from a component
* get_current_zone_temperature - Get the current temperature from (the first component in) a zone
