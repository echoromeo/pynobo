# Nobø Hub / Nobø Energy Control Websocket Interface

This system/service/software is not officially supported or endorsed by Glen Dimplex Nordic AS, and I am not an official partner of Glen Dimplex Nordic AS

[The API for Nobø Hub can be found here][api]

[The source for this project is available here][src]

[api]: https://www.glendimplex.no/media/15650/nobo-hub-api-v-1-1-integration-for-advanced-users.pdf
[src]: https://github.com/echoromeo/pynobo

To get started, call using the three last digits in the hub serial

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

