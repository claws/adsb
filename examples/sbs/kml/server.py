'''
This example implements an application that exposes a web service which
supplies KML data produced from the data stored in a adsb session.

The example has dependencies on ``simplekml`` and ``quart``. These can be
installed using:

.. code-block:: python

    (venv) $ pip install -r requirements

You must supply the SBS message source and the ADSB receiver location as a
lat,lon value when starting the application.

.. code-block:: console

    (venv) $ python server.py --sbs-host=127.0.0.1 --location="-23.7,133.8"

Fetch the KML content that contains the Network Link within it.

.. code-block:: console

    $ curl http://127.0.0.1:8080/kml > adsb.kml
    <?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      ...
    </kml>

This content can be written to a file called ``adsb.kml`` which can then be
loaded into Google Earth.

Once loaded into Google Earth it will use the network link information
within to periodically refresh the display by accessing the network link URL
defined in the ``adsb.kml`` file.

You can observe the content being sent to Google Earth by accessing the KML
update route:

.. code-block:: console

    $ curl http://127.0.0.1:8080/kml_update
    <?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
      ...
    </kml>

'''

import argparse
import asyncio
import io
import logging
import ssl
import adsb
import simplekml

from quart import Quart, request, render_template, Response, url_for
from asyncio import AbstractEventLoop
from ssl import SSLContext
from typing import Dict, Set, Tuple
from adsb.constants import EARTH_RADIUS
from adsb.mypy_types import PositionType
from adsb.utils import feet_to_meters


logger = logging.getLogger(__name__)


kml_mimetype = 'application/vnd.google-earth.kml+xml'
kmz_mimetype = 'application/vnd.google-earth.kmz'
SUPPORTED_MIMETYPES = (kmz_mimetype, kml_mimetype)


class KMLServer(Quart):
    '''
    Create a web service that can produce KML to satisfy the KML
    NetworkLink capability to dynamically update screen content.
    '''

    def __init__(self,
                 import_name: str,
                 sbs_host: str = 'localhost',
                 sbs_port: int = 30003,
                 location: PositionType = None,
                 refresh_interval: int = 10,
                 kmz: bool = True,
                 **kwargs) -> None:
        '''
        Initialise the KML service.

        :param host: The SBS server host to connect to.

        :param port: The SBS server port to connect to.

        :param location: A (lat,lon) tuple to use as the ADSB receiver
          location.

        :param refresh_interval: a duration in seconds that is inserted into
          the KML file. This will trigger a user of the KML file to fetch
          new data from the network link URL.

        :raises: Exception if the registry object is not an instance of the
          Registry type.
        '''
        super().__init__(import_name, **kwargs)
        self.sbs_host = sbs_host
        self.sbs_port = sbs_port
        self.receiver_latitude, self.receiver_longitude = location
        self.refresh_interval = refresh_interval

        self.loop = asyncio.get_event_loop()
        self.add_url_rule('/kml', self.handle_kml)
        self.add_url_rule('/kml_update', self.handle_kml_update)

        self.sbssession = adsb.session.Session(
            origin=(self.receiver_latitude, self.receiver_longitude))

        # Schedule the SBS session to start before accepting any requests.
        self.before_first_request(self._start)

    async def handle_kml(self):
        ''' Handle a request to the /kml route '''
        # update_url = url_for('handle_kml_update', _external=True, _scheme='http')
        headers = {'Content-type': kml_mimetype}
        content = await render_template(
            'adsb.kml',
            kml_update_url=f'http://127.0.0.1:8080/kml_update',
            update_interval=self.refresh_interval,
            # lookat point's latitude on the earth's surface,
            latitude=self.receiver_latitude,
            # lookat point's longitude on the earth's surface,
            longitude=self.receiver_longitude,
            # lookat point's distance from the earth's surface, in meters.
            # altitude=0.0,
            # Distance in meters from the point specified by <longitude>,
            # <latitude>, and <altitude> to the LookAt position.
            range=250_000.0,
            # A <tilt> value of 0 degrees indicates viewing from directly
            # above. A <tilt> value of 90 degrees indicates viewing along
            # the horizon.
            # tilt=40.0,
            # heading=0.0
            )
        return Response(content, headers=headers)

    async def handle_kml_update(self):
        ''' Handle a request to the /kml_update route. '''
        print(request.headers)

        mimetype = kml_mimetype
        accept_items = request.headers.get('Accept')
        # strip anything after ; for each item
        accept_mimetypes = [item.split(';')[0] for item in accept_items.split(',')]
        for accept_mimetype in SUPPORTED_MIMETYPES:
            if accept_mimetype in accept_mimetypes:
                mimetype = accept_mimetype
                break

        # The ACCEPT header received from GoogleEarth seems non-standard by using
        # ;googleearth=context.kml and ;googleearth=context.kmz where ;q= is
        # expected. This breaks the Quart accept_mimetypes parser function.
        # accept_mimetypes = request.accept_mimetypes
        # mimetype = request.accept_mimetypes.best_match(
        #     SUPPORTED_MIMETYPES, default=kml_mimetype)

        try:
            kml = simplekml.Kml(name='adsb')
            for hex_ident, ac in self.sbssession.aircraft.items():
                if ac.history:
                    coords = []
                    # Discard history points that do not have lat, lon and
                    # altitude fields.
                    for timestamp, lat, lon, alt in ac.history:
                        if lat and lon and alt:
                            coords.append((lon, lat, feet_to_meters(alt)))

                    # Add a track header symbol
                    if coords:
                        latest_pos = coords[-1]
                        pnt = kml.newpoint(
                            name=hex_ident, description=hex_ident,
                            coords=[latest_pos])  # lon, lat, optional height
                        pnt.altitudemode = simplekml.AltitudeMode.relativetoground
                        pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/open-diamond.png'
                        pnt.style.iconstyle.icon.heading = ac.track
                        lin = kml.newlinestring(
                            name=f"{hex_ident} history", coords=coords)
                        lin.style.linestyle.color = simplekml.Color.azure
                        # lin.extrude = 1  # drop line down to earth
                        lin.altitudemode = simplekml.AltitudeMode.relativetoground

            # kml.save('adsb.kml')  # debug purpose only

            if mimetype == kmz_mimetype:
                _kmz_data = io.BytesIO()
                kml.savekmz(_kmz_data)
                content = _kmz_data.getvalue()
                del _kmz_data
            else:
                content = kml.kml()

        except Exception:
            logger.exception('Error generating KML')
            # Follow the advise from KML docs. A simple way to handle errors
            # is to pass the server's error as the text for a folder name.
            # This is more informative (and more user-friendly) than letting
            # the connection drop.
            content = '<Folder><name>ADSB data inaccessible</name></Folder>'
            mimetype = kml_mimetype

        print('/kml_update route accessed')
        headers = {
            'Content-type': mimetype,
            'Access-Control-Allow-Origin': '*'}  # enable CORS
        return Response(content, headers=headers)

    async def _start(self) -> None:
        await self.sbssession.connect(self.sbs_host, self.sbs_port)

    async def _stop(self, exc) -> None:
        ''' Shutdown the KML server '''
        logger.debug('KML server stopping')
        await self.sbssession.close()
        logger.debug('KML server stopped')


ARGS = argparse.ArgumentParser(description='ADSB KML Service')
ARGS.add_argument(
    '--bind-address',
    action="store",
    default='localhost',
    help='Bind address for web service')
ARGS.add_argument(
    '--bind-port',
    action="store",
    default=8080,
    type=int,
    help='Bind port for web service')
ARGS.add_argument(
    '--ssl',
    action="store_true",
    help='Run ssl mode.')
ARGS.add_argument(
    '--sslcert',
    action="store",
    dest='certfile',
    help='SSL cert file.')
ARGS.add_argument(
    '--sslkey',
    action="store",
    dest='keyfile',
    help='SSL key file.')
ARGS.add_argument(
    '--sbs-host',
    type=str,
    default='localhost',
    help='The SBS host name')
ARGS.add_argument(
    '--sbs-port',
    type=int,
    default=30003,
    help='The SBS port number. Default is 30003.')
ARGS.add_argument(
    '--location',
    type=str,
    metavar="lat,lon",
    default=None,
    help="A (lat,lon) location to use as the origin.")


if __name__ == '__main__':

    args = ARGS.parse_args()

    if args.ssl:
        resources_dir = os.path.dirname(os.path.abspath(__file__))
        certfile = args.certfile or os.path.join(resources_dir, 'sample.crt')
        keyfile = args.keyfile or os.path.join(resources_dir, 'sample.key')
        sslcontext = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        sslcontext.load_cert_chain(certfile, keyfile)
    else:
        sslcontext = None

    if args.location is None:
        raise Exception('ADSB receiver location must be supplied')

    lat, lon = args.location.split(',')
    args.location = (float(lat), float(lon))

    app = KMLServer('kml_server',
                    sbs_host=args.sbs_host,
                    sbs_port=args.sbs_port,
                    location=args.location)
    app.config['SERVER_NAME'] = f'{args.bind_address}:{args.bind_port}'
    print('KML server starting...')
    app.run(host=args.bind_address,
            port=args.bind_port,
            ssl=sslcontext)
