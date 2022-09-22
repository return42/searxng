# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
"""DuckDuckGo Weather"""

from json import loads
from urllib.parse import quote

from datetime import datetime

about = {
    "website": 'https://duckduckgo.com/',
    "wikidata_id": 'Q12805',
    "official_api_documentation": None,
    "use_official_api": True,
    "require_api_key": False,
    "results": "JSON",
}

categories = ["weather"]

url = "https://duckduckgo.com/js/spice/forecast/{query}/{lang}"


def request(query, params):
    params["url"] = url.format(query=quote(query), lang=params['language'].split('-')[0])

    return params


def f_to_c(temperature):
    return "%.2f" % ((temperature - 32) / 1.8)


def map_ddw_weather_data(w_item: dict):

    # WeatherPeriodType

    w_period = {
        'air_temperature_max': {'F': w_item.get('temperatureHigh')},
        'air_temperature_min': {'F': w_item.get('temperatureLow')},
        'precipitation_amount': w_item.get('precipIntensity'),
        'precipitation_amount_max': w_item.get('precipIntensityMax'),
        'probability_of_precipitation': w_item.get('precipIntensity'),
        'probability_of_thunder': None,
        'ultraviolet_index_clear_sky_max': w_item.get('uvIndex'),
    }

    # normalize the values

    if w_period['air_temperature_max']['F'] is not None:
        w_period['air_temperature_max']['C'] = f_to_c(w_period['air_temperature_max']['F'])

    if w_period['air_temperature_min']['F'] is not None:
        w_period['air_temperature_min']['C'] = f_to_c(w_period['air_temperature_min']['F'])

    if w_period['precipitation_amount'] is not None:
        w_period['precipitation_amount'] = w_period['precipitation_amount'] * 1000

    if w_period['precipitation_amount_max'] is not None:
        w_period['precipitation_amount_max'] = w_period['precipitation_amount_max'] * 1000

    if w_period['precipIntensity'] is not None:
        w_period['precipIntensity'] = w_period['precipIntensity'] * 100

    # WeatherInstantType

    w_instant = {
        'air_pressure_at_sea_level': w_item.get('pressure'),
        'air_temperature': w_item.get('temperature'),
        'air_temperature_percentile_10': None,
        'air_temperature_percentile_90': None,
        'cloud_area_fraction': w_item.get('cloudCover'),
        'cloud_area_fraction_high': None,
        'cloud_area_fraction_low': None,
        'cloud_area_fraction_medium': None,
        'dew_point_temperature': {'F': w_item.get('dewPoint')},
        'fog_area_fraction': None,
        'relative_humidity': w_item.get('humidity'),
        'wind_from_direction': w_item.get('windBearing'),
        'wind_speed': w_item.get('windSpeed'),
        'wind_speed_of_gust': w_item.get('windGust'),
        'wind_speed_percentile_10': None,
        'wind_speed_percentile_90': None,
    }

    # normalize the values

    if w_instant['cloud_area_fraction'] is not None:
        w_instant['cloud_area_fraction'] = w_instant['cloud_area_fraction'] * 100

    if w_instant['dew_point_temperature']['F'] is not None:
        w_instant['dew_point_temperature']['C'] = f_to_c(w_instant['dew_point_temperature']['F'])

    if w_instant['relative_humidity'] is not None:
        w_instant['relative_humidity'] = w_instant['relative_humidity'] * 100

    # WeatherSummaryType

    # TODO ...
    w_summary = {}

    # "icon": "clear-night",
    # "icon": "rain",
    # "icon": "clear-night",
    # "icon": "partly-cloudy-night",
    # "icon": "partly-cloudy-day",
    # cloudy

    return w_period, w_instant, w_summary


def response(resp):
    results = []

    if resp.text.strip() == "ddg_spice_forecast();":
        return []

    result = loads(resp.text[resp.text.find('{') : resp.text.rfind('}') + 1])

    # from json import dump
    # with open("ddgw.json", "w") as f:
    #     logger.debug("dump ddgw.json ...")
    #     dump(result, f, indent=2)

    current = result["currently"]

    forecast_data = []
    last_date = None
    current_data = {}

    for time in result['hourly']['data']:
        current_time = datetime.fromtimestamp(time['time'])

        if last_date != current_time.date():
            if last_date is not None:
                forecast_data.append(current_data)

            today = next(
                day
                for day in result['daily']['data']
                if datetime.fromtimestamp(day['time']).date() == current_time.date()
            )

            current_data = {
                'date': current_time.strftime('%Y-%m-%d'),
                'metric': {
                    'min_temp': f_to_c(today['temperatureLow']),
                    'max_temp': f_to_c(today['temperatureHigh']),
                },
                'uv_index': today['uvIndex'],
                'sunrise': datetime.fromtimestamp(today['sunriseTime']).strftime('%H:%M'),
                'sunset': datetime.fromtimestamp(today['sunsetTime']).strftime('%H:%M'),
                'forecast': [],
            }

        current_data['forecast'].append(
            {
                'time': current_time.strftime('%H:%M'),
                'metric': {
                    'temperature': f_to_c(time['temperature']),
                    'feels_like': f_to_c(time['apparentTemperature']),
                    'wind_speed': '%.2f' % (time['windSpeed'] * 1.6093440006147),
                    'visibility': time['visibility'],
                },
                'imperial': {
                    'temperature': time['temperature'],
                    'feels_like': time['apparentTemperature'],
                    'wind_speed': time['windSpeed'],
                },
                'condition': time['summary'],
                'wind_direction': time['windBearing'],
                'humidity': time['humidity'] * 100,
            }
        )

        last_date = current_time.date()

    forecast_data.append(current_data)

    results.append(
        {
            'template': 'weather.html',
            'location': result['flags']['ddg-location'],
            'currently': {
                'metric': {
                    'temperature': f_to_c(current['temperature']),
                    'feels_like': f_to_c(current['apparentTemperature']),
                    'wind_speed': '%.2f' % (current['windSpeed'] * 1.6093440006147),
                    'visibility': current['visibility'],
                },
                'imperial': {
                    'temperature': current['temperature'],
                    'feels_like': current['apparentTemperature'],
                    'wind_speed': current['windSpeed'],
                },
                'condition': current['summary'],
                'wind_direction': current['windBearing'],
                'humidity': current['humidity'] * 100,
            },
            'forecast': forecast_data,
        }
    )

    return results
