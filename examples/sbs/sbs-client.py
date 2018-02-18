#!/usr/bin/env python3
'''
This script demonstrates how the SBS Client can be used to collect ADSB
messages from a SBS server. The SBS Client provides its user with the
ability to:

  1. obtain raw SBS messages as a line of text,
  2. obtain a processed message as a SBSMessage Python object.
  3. record messages to a log file for later use.

To collect SBS messages and parse them into a SBSMessage object
and then write them to the terminal use the following command.

..code-block:: console

    (venv) $ python sbs-client.py --host=127.0.0.1 --processed
    {"message_type": "MSG", "transmission_type": 6, "session_id": 1, "aircraft_id": 1, "hex_ident": "7C7C76", "flight_id": 1, "generated_date": {"__type__": "date", "year": 2018, "month": 2, "day": 18}, "generated_time": {"__type__": "time", "hour": 21, "minute": 21, "second": 6, "microsecond": 987000}, "logged_date": {"__type__": "date", "year": 2018, "month": 2, "day": 18}, "logged_time": {"__type__": "time", "hour": 21, "minute": 21, "second": 7, "microsecond": 5000}, "callsign": null, "altitude": null, "ground_speed": null, "track": null, "lat": null, "lon": null, "vertical_rate": null, "squawk": "7220", "alert": false, "emergency": false, "spi": false, "is_on_ground": null}
    {"message_type": "MSG", "transmission_type": 8, "session_id": 1, "aircraft_id": 1, "hex_ident": "7C7C76", "flight_id": 1, "generated_date": {"__type__": "date", "year": 2018, "month": 2, "day": 18}, "generated_time": {"__type__": "time", "hour": 21, "minute": 21, "second": 7, "microsecond": 30000}, "logged_date": {"__type__": "date", "year": 2018, "month": 2, "day": 18}, "logged_time": {"__type__": "time", "hour": 21, "minute": 21, "second": 7, "microsecond": 57000}, "callsign": null, "altitude": null, "ground_speed": null, "track": null, "lat": null, "lon": null, "vertical_rate": null, "squawk": null, "alert": null, "emergency": null, "spi": null, "is_on_ground": 0}
    ^C
    SIGINT, stopping.


To collect SBS messages from a SBS server and then dump the raw messages to
the terminal use the following command.

..code-block:: console

    (venv) $ python sbs-client.py --host=127.0.0.1 --raw
    b'MSG,6,1,1,7C7C76,1,2018/02/18,21:21:06.987,2018/02/18,21:21:07.005,,,,,,,,7220,0,0,0,'
    b'MSG,8,1,1,7C7C76,1,2018/02/18,21:21:07.030,2018/02/18,21:21:07.057,,,,,,,,,,,,0'
    ^C
    SIGINT, stopping.


To collect SBS messages from a SBS server and then record them into a
log file use the following command.

..code-block:: console

    (venv) $ python sbs-client.py --host=127.0.0.1 --record --record-file=sbs-messages.txt

'''

import argparse
import asyncio
import functools
import signal

from adsb import sbs


def handle_raw_msg(msg: bytes):
    ''' Handle a raw SBS message '''
    print(msg)


def handle_parsed_msg(msg: sbs.message.SBSMessage):
    ''' Handle a processed SBS message '''
    # We could call sbs.message.toString(msg) but the output would look
    # just like to raw data. Instead, print out the message as JSON to
    # convey that it has been parsed.
    print(sbs.json_utils.dumps(msg))


ARGS = argparse.ArgumentParser(description='SBS Client Example')
ARGS.add_argument(
    '--host',
    metavar='<host>',
    type=str,
    default='localhost',
    help='The SBS host name')
ARGS.add_argument(
    '--port',
    metavar='<port>',
    type=int,
    default=30003,
    help='The SBS port number. Default is 30003.')
ARGS.add_argument(
    '--raw',
    action="store_true",
    default=False,
    help="Dump raw SBS messages to stdout")
ARGS.add_argument(
    '--processed',
    action="store_true",
    default=False,
    help="Dump processed SBS messages to stdout")
ARGS.add_argument(
    '--record',
    action="store_true",
    help="Record SBS messages to a log file")
ARGS.add_argument(
    '--record-file',
    type=str,
    default=None,
    help="Record SBS messages into this file")


if __name__ == '__main__':

    args = ARGS.parse_args()

    loop = asyncio.get_event_loop()

    client = sbs.client.Client(
        host=args.host,
        port=args.port,
        on_raw_msg_callback=handle_raw_msg if args.raw else None,
        on_msg_callback=handle_parsed_msg if args.processed else None,
        record=args.record,
        record_file=args.record_file)

    def signal_handler(signame, client, loop):
        print("\n{}, stopping.".format(signame))
        loop.stop()

    for signame in ('SIGINT', 'SIGTERM'):
        signum = getattr(signal, signame)
        handler = functools.partial(signal_handler, signame, client, loop)
        loop.add_signal_handler(signum, handler)

    loop.run_until_complete(client.start())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print('KeyboardInterrupt')
        pass
    except RuntimeError:
        # Ctrl+c will trigger this
        print('RuntimeError')
        pass
    finally:
        loop.run_until_complete(client.stop())
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
