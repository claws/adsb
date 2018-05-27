"""
The JSON encoding and decoding functions are modelled after the json package
which use *loads* to parse a message from a string and *dumps* to encode a
message to a string.
"""
import datetime
import json
from .message import SBSMessage
from typing import Union


class DateTimeAwareEncoder(json.JSONEncoder):
    """ Extend JSON encoder to support encoding datetime and timedelta objects """

    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return {
                "__type__": "datetime",
                "year": obj.year,
                "month": obj.month,
                "day": obj.day,
                "hour": obj.hour,
                "minute": obj.minute,
                "second": obj.second,
                "microsecond": obj.microsecond,
            }
        elif isinstance(obj, datetime.time):
            return {
                "__type__": "time",
                "hour": obj.hour,
                "minute": obj.minute,
                "second": obj.second,
                "microsecond": obj.microsecond,
            }
        elif isinstance(obj, datetime.date):
            return {
                "__type__": "date",
                "year": obj.year,
                "month": obj.month,
                "day": obj.day,
            }
        elif isinstance(obj, datetime.timedelta):
            return {
                "__type__": "timedelta",
                "days": obj.days,
                "seconds": obj.seconds,
                "microseconds": obj.microseconds,
            }
        else:
            return super().default(obj)


class DateTimeAwareDecoder(json.JSONDecoder):
    """ Extend JSON decoder to support decoding datetime and timedelta objects """

    def __init__(self):
        super().__init__(object_hook=self.dict_to_object)

    def dict_to_object(self, d):
        if "__type__" not in d:
            return d
        _type = d.pop("__type__")
        if _type == "datetime":
            return datetime.datetime(**d)
        elif _type == "time":
            return datetime.time(**d)
        elif _type == "date":
            return datetime.date(**d)
        elif _type == "timedelta":
            return datetime.timedelta(**d)
        else:
            # Unexpected... reconstruct.
            d["__type__"] = _type
        return d


def loads(line: Union[bytes, str]) -> SBSMessage:
    """ Deserialize a JSON format string into a SBSMessage """
    if isinstance(line, bytes):
        line = line.decode()
    d = json.loads(line, cls=DateTimeAwareDecoder)
    m = SBSMessage(**d)
    return m


def dumps(m: SBSMessage, indent: int = None, sort_keys: bool = False) -> str:
    """ Serialize a SBSMessage object into a JSON format string """
    return json.dumps(
        dict(m._asdict().items()),
        indent=indent,
        sort_keys=sort_keys,
        cls=DateTimeAwareEncoder,
    )
