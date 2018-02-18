
import datetime
from typing import Dict, Set, Tuple

LatitudeType = float
LongitudeType = float
AltitudeType = float
PositionType = Tuple[LatitudeType, LongitudeType]
HistoryPointType = Tuple[datetime.datetime, LatitudeType, LongitudeType, AltitudeType]
