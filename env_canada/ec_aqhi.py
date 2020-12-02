from datetime import datetime, timezone
import logging
import xml.etree.ElementTree as et

from aiohttp import ClientSession
from geopy import distance
import requests

AQHI_SITE_LIST_URL = "https://dd.weather.gc.ca/air_quality/doc/AQHI_XML_File_List.xml"
AQHI_OBSERVATION_URL = "https://dd.weather.gc.ca/air_quality/aqhi/{}/observation/realtime/xml/AQ_OBS_{}_CURRENT.xml"
AQHI_FORECAST_URL = "https://dd.weather.gc.ca/air_quality/aqhi/{}/forecast/realtime/xml/AQ_FCST_{}_CURRENT.xml"

LOG = logging.getLogger(__name__)


def timestamp_to_datetime(timestamp):
    dt = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
    dt = dt.replace(tzinfo=timezone.utc)
    return dt


class ECAirQuality(object):

    """Get air quality data from Environment Canada."""

    def __init__(self, zone_id=None, region_id=None, coordinates=None, language="EN"):
        """Initialize the data object."""
        self.language = language.upper()

        if zone_id and region_id:
            self.zone_id = zone_id
            self.region_id = region_id.upper()
        else:
            self.zone_id = None
            self.region_id = None
            self.coordinates = coordinates

        self.current = None
        self.current_timestamp = None
        self.forecasts = dict(daily={}, hourly={})

    async def get_aqhi_data(self, url):
        async with ClientSession() as session:
            response = await session.get(
                url.format(self.zone_id, self.region_id), timeout=10
            )
            if response.ok:
                result = await response.read()
                aqhi_xml = result.decode("ISO-8859-1")
                return et.fromstring(aqhi_xml)
            else:
                LOG.warning("Error fetching AQHI data")
                return None

    async def update(self):

        if not (self.zone_id and self.region_id):
            await self.find_closest_region(*self.coordinates)

        # Update AQHI current condition

        aqhi_current = await self.get_aqhi_data(url=AQHI_OBSERVATION_URL)
        element = aqhi_current.find("airQualityHealthIndex")
        if element is not None:
            self.current = float(element.text)
        else:
            self.current = None

        element = aqhi_current.find("./dateStamp/UTCStamp")
        if element is not None:
            self.current_timestamp = timestamp_to_datetime(element.text)
        else:
            self.current_timestamp = None

        # Update AQHI forecasts
        aqhi_forecast = await self.get_aqhi_data(url=AQHI_FORECAST_URL)

        # Update AQHI daily forecasts
        for f in aqhi_forecast.findall("./forecastGroup/forecast"):
            for p in f.findall("./period"):
                if self.language == p.attrib["lang"]:
                    period = p.attrib["forecastName"]
            self.forecasts["daily"][period] = int(f.findtext("./airQualityHealthIndex"))

        # Update AQHI hourly forecasts
        for f in aqhi_forecast.findall("./hourlyForecastGroup/hourlyForecast"):
            self.forecasts["hourly"][timestamp_to_datetime(f.attrib["UTCTime"])] = int(
                f.text
            )

    async def get_aqhi_regions(self):
        """Get list of all AQHI regions from Environment Canada, for auto-config."""
        zone_name_tag = "name_%s_CA" % self.language.lower()
        region_name_tag = "name%s" % self.language.title()

        regions = []
        try:
            async with ClientSession() as session:
                response = await session.get(AQHI_SITE_LIST_URL, timeout=10)
                result = await response.read()
        except requests.exceptions.RequestException as e:
            LOG.warning("Unable to retrieve AQHI regions: %s", e)
            return None

        site_xml = result.decode("utf-8")
        xml_object = et.fromstring(site_xml)

        for zone in xml_object.findall("./EC_administrativeZone"):
            _zone_attribs = zone.attrib
            _zone_attrib = {
                "abbreviation": _zone_attribs["abreviation"],
                "zone_name": _zone_attribs[zone_name_tag],
            }
            for region in zone.findall("./regionList/region"):
                _region_attribs = region.attrib

                _region_attrib = {
                    "region_name": _region_attribs[region_name_tag],
                    "cgndb": _region_attribs["cgndb"],
                    "latitude": float(_region_attribs["latitude"]),
                    "longitude": float(_region_attribs["longitude"]),
                }
                _children = list(region)
                for child in _children:
                    _region_attrib[child.tag] = child.text
                _region_attrib.update(_zone_attrib)
                regions.append(_region_attrib)
        return regions

    async def find_closest_region(self, lat, lon):
        """Return the AQHI region and site ID of the closest site."""
        region_list = await self.get_aqhi_regions()

        def site_distance(site):
            """Calculate distance to a region."""
            return distance.distance((lat, lon), (site["latitude"], site["longitude"]))

        closest = min(region_list, key=site_distance)
        self.zone_id = closest["abbreviation"]
        self.region_id = closest["cgndb"]
