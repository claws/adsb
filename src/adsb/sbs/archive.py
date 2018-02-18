'''
This module implements a SBS message archive writing and reading capability.
It can be used to save messages to file so that they can be replayed or
analysed at a later time.

An archive is simply a recording of the message lines that were received
from the server. Each message line item is prefixed with a timestamp and
terminated with a new line. By associating a timestamp with the message in the
log file the messages can then be replayed at different rates.
'''

import datetime
import logging
import os


logger = logging.getLogger(__name__)


class RotatingArchiveFileHandler(object):
    '''
    Base class for handlers that record to disk files and rotate log files
    at a certain point.

    Handler for logging to a set of files, which switches from one file
    to the next when the current file reaches a certain size.

    Shamelessly duplicated from the Python standard library logging module
    with deep class hierarchy condensed and stripped of logger record
    specifics.
    '''

    terminator = '\r\n'  # Use the same delimiter as used on SBS stream

    def __init__(self,
                 filename,
                 mode='a',
                 maxBytes=0,
                 backupCount=0,
                 encoding=None):
        '''
        Open the specified file and use it as the stream for logging.

        By default, the file grows indefinitely. You can specify particular
        values of maxBytes and backupCount to allow the file to rollover at
        a predetermined size.

        Rollover occurs whenever the current log file is nearly maxBytes in
        length. If backupCount is >= 1, the system will successively create
        new files with the same pathname as the base file, but with extensions
        ".1", ".2" etc. appended to it. For example, with a backupCount of 5
        and a base file name of "app.log", you would get "app.log",
        "app.log.1", "app.log.2", ... through to "app.log.5". The file being
        written to is always "app.log" - when it gets filled up, it is closed
        and renamed to "app.log.1", and if files "app.log.1", "app.log.2" etc.
        exist, then they are renamed to "app.log.2", "app.log.3" etc.
        respectively.

        If maxBytes is zero, rollover never occurs.
        '''
        # If rotation/rollover is wanted, it doesn't make sense to use another
        # mode. If for example 'w' were specified, then if there were multiple
        # runs of the calling application, the logs from previous runs would be
        # lost if the 'w' is respected, because the log file would be truncated
        # on each run.
        if maxBytes > 0:
            mode = 'a'
        self.baseFilename = os.path.abspath(filename)
        self.mode = mode
        self.encoding = encoding
        self.stream = self._open()
        self.namer = None
        self.rotator = None
        self.maxBytes = maxBytes
        self.backupCount = backupCount

    def flush(self):
        '''
        Flushes the stream.
        '''
        if self.stream and hasattr(self.stream, "flush"):
            self.stream.flush()

    def close(self):
        '''
        Closes the stream.
        '''
        if self.stream:
            self.flush()
            if hasattr(self.stream, "close"):
                self.stream.close()
            self.stream = None

    def _open(self):
        '''
        Open the base file with the (original) mode and encoding.
        Return the resulting stream.
        '''
        return open(self.baseFilename, self.mode, encoding=self.encoding)

    def emit(self, record: str):
        '''
        Emit a record to the log file, catering for rollover as described
        in doRollover().

        In this case the record is a SBS format message line. It does not
        require any extra formatting. This method overrides the default
        logging behaviour so that SBS messsages can be written to file
        directly.

        A timestamp, in UTC, is added to facilitate replaying a session log
        at a rate faster than real time while keeping the relative spacing
        between the messages.
        '''
        if self.stream is None:
            logger.warning(
                'Attempted to write to archive but no stream exists')
            return

        try:
            if self.shouldRollover(record):
                self.doRollover()
            stream = self.stream
            msg = record
            timestamp = datetime.datetime.now(tz=datetime.timezone.utc)
            stream.write(f'{timestamp.isoformat()},{msg}{self.terminator}')
            self.flush()
        except Exception:
            logger.exception('Problem storing message to session archive')

    def rotation_filename(self, default_name):
        '''
        Modify the filename of a log file when rotating.

        This is provided so that a custom filename can be provided.

        The default implementation calls the 'namer' attribute of the
        handler, if it's callable, passing the default name to
        it. If the attribute isn't callable (the default is None), the name
        is returned unchanged.

        :param default_name: The default name for the log file.
        '''
        if not callable(self.namer):
            result = default_name
        else:
            result = self.namer(default_name)
        return result

    def rotate(self, source, dest):
        '''
        When rotating, rotate the current log.

        The default implementation calls the 'rotator' attribute of the
        handler, if it's callable, passing the source and dest arguments to
        it. If the attribute isn't callable (the default is None), the source
        is simply renamed to the destination.

        :param source: The source filename. This is normally the base
                       filename, e.g. 'test.log'
        :param dest:   The destination filename. This is normally
                       what the source is rotated to, e.g. 'test.log.1'.
        '''
        if not callable(self.rotator):
            if os.path.exists(source):
                os.rename(source, dest)
        else:
            self.rotator(source, dest)

    def doRollover(self):
        '''
        Do a rollover, as described in __init__().
        '''
        if self.stream:
            self.stream.close()
            self.stream = None
        if self.backupCount > 0:
            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename("%s.%d" % (self.baseFilename, i))
                dfn = self.rotation_filename("%s.%d" % (self.baseFilename,
                                                        i + 1))
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)
            dfn = self.rotation_filename(self.baseFilename + ".1")
            if os.path.exists(dfn):
                os.remove(dfn)
            self.rotate(self.baseFilename, dfn)
        self.stream = self._open()

    def shouldRollover(self, record):
        '''
        Determine if rollover should occur.

        Basically, see if the supplied record would cause the file to exceed
        the size limit we have.
        '''
        if self.stream is None:                 # delay was set...
            self.stream = self._open()
        if self.maxBytes > 0:                   # are we rolling over?
            msg = "{}{}".format(record, self.terminator)
            self.stream.seek(0, 2)  # due to non-posix-compliant Windows feature
            if self.stream.tell() + len(msg) >= self.maxBytes:
                return 1
        return 0


def read_archive(archive_file):
    '''
    This generator yields lines from a session archive log file.
    Each line is returned as a 2-tuple containing a UTC timestamp
    and the SBS format message bytes.

    :param archive_file: An archive file
    '''
    if os.path.exists(archive_file):
        with open(archive_file, 'rb') as f:
            for line in f:
                timestamp, msg_bytes = line.split(b',', 1)
                yield timestamp.decode(), msg_bytes
