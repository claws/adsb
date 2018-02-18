'''

To start a session use the following command.

..code-block:: console

    (venv) $ python sbs-session.py --host=127.0.0.1
    ^C
    SIGINT, stopping.

'''
import argparse
import asyncio
import functools
import signal

from adsb import sbs


def handle_raw_msg(msg: str):
    ''' Handle a raw SBS message '''
    print(msg)


def handle_parsed_msg(msg: sbs.message.SBSMessage):
    ''' Handle a processed SBS message '''
    print(sbs.json_utils.dumps(msg))
    print(sbs.message.toString(m))


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
    '--record',
    action="store_true",
    help="Record SBS messages to a log file")
ARGS.add_argument(
    '--record-file',
    type=str,
    default=None,
    help="Record SBS messages into this file")


async def session_aircraft_dumper_task(session, interval=5.0):
    '''
    Dump the session aircraft details at regular intervals.

    This is a simple debug function.
    '''
    while True:
        if session.aircraft:
            for ident, ac in session.aircraft.items():
                print(ac)
        await asyncio.sleep(interval)


if __name__ == '__main__':

    args = ARGS.parse_args()

    loop = asyncio.get_event_loop()

    session = sbs.session.Session(
        record=args.record,
        record_file=args.record_file)

    def signal_handler(signame, session, loop):
        print("\n{}, stopping.".format(signame))
        loop.stop()

    for signame in ('SIGINT', 'SIGTERM'):
        signum = getattr(signal, signame)
        handler = functools.partial(signal_handler, signame, session, loop)
        loop.add_signal_handler(signum, handler)

    loop.run_until_complete(session.connect(args.host, args.port))

    # Start a debug task to periodically dump session aircraft to terminal
    asyncio.ensure_future(session_aircraft_dumper_task(session))

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
        loop.run_until_complete(session.disconnect())
        loop.run_until_complete(session.close())
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
