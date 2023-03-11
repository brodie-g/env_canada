import asyncio

import pytest

from env_canada import ec_weather, ECWeather


def test_get_ec_sites():
    sites = asyncio.run(ec_weather.get_ec_sites())
    assert len(sites) > 0


@pytest.mark.parametrize(
    "init_parameters", [{"coordinates": (50, -100)}, {"station_id": "ON/s0000430"}]
)
def test_ecweather(init_parameters):
    weather = ECWeather(**init_parameters)
    assert isinstance(weather, ECWeather)


@pytest.fixture()
def test_weather():
    return ECWeather(coordinates=(50, -100))


@pytest.fixture()
def test_weather_city():
    return ECWeather(city='Halifax')


def test_update(test_weather):
    asyncio.run(test_weather.update())
    assert test_weather.conditions
    assert test_weather.daily_forecasts
    assert test_weather.hourly_forecasts


def test_update_city(test_weather_city):
    asyncio.run(test_weather_city.update())
    assert test_weather_city.conditions
    assert test_weather_city.daily_forecasts
    assert test_weather_city.hourly_forecasts

def test_forecast_pretty(test_weather_city):
    asyncio.run(test_weather_city.update())
    assert test_weather_city.daily_forecasts_pretty()
