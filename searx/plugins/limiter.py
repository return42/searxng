# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
# pyright: basic
"""Some bot protection / rate limitation

To monitor rate limits and protect privacy the IP addresses are getting stored
with a hash so the limiter plugin knows who to block.  A redis database is
needed to store the hash values.

Enable the plugin in ``settings.yml``:

- ``server.limiter: true``
- ``redis.url: ...`` check the value, see :ref:`settings redis`
"""

import re
from flask import request

from searx import redisdb
from searx.plugins import logger
from searx.redislib import incr_sliding_window

name = "Request limiter"
description = "Limit the number of request"
default_on = False
preference_section = 'service'
logger = logger.getChild('limiter')

block_user_agent = re.compile(
    r'('
    + r'unknown'
    + r'|[Cc][Uu][Rr][Ll]|[wW]get|Scrapy|splash|JavaFX|FeedFetcher|python-requests|Go-http-client|Java|Jakarta|okhttp'
    + r'|HttpClient|Jersey|Python|libwww-perl|Ruby|SynHttpClient|UniversalFeedParser|Googlebot|GoogleImageProxy'
    + r'|bingbot|Baiduspider|yacybot|YandexMobileBot|YandexBot|Yahoo! Slurp|MJ12bot|AhrefsBot|archive.org_bot|msnbot'
    + r'|MJ12bot|SeznamBot|linkdexbot|Netvibes|SMTBot|zgrab|James BOT|Sogou|Abonti|Pixray|Spinn3r|SemrushBot|Exabot'
    + r'|ZmEu|BLEXBot|bitlybot'
    # unmaintained Farside instances
    + r'|'
    + re.escape(r'Mozilla/5.0 (compatible; Farside/0.1.0; +https://farside.link)')
    + '|.*PetalBot.*'
    + r')'
)

ip_block_list = [
    '09.248.205.4',
    '103.103.244.112',
    '104.144.34.237',
    '104.210.133.1',
    '107.181.128.96',
    '109.248.12.120',
    '109.248.128.149',
    '109.248.13.136',
    '109.248.13.174',
    '109.248.138.36',
    '109.248.139.124',
    '109.248.139.55',
    '109.248.139.75',
    '109.248.139.98',
    '109.248.14.177',
    '109.248.14.67',
    '109.248.142.31',
    '109.248.143.220',
    '109.248.143.224',
    '109.248.15.145',
    '109.248.15.153',
    '109.248.15.86',
    '109.248.166.186',
    '109.248.166.31',
    '109.248.167.105',
    '109.248.204.204',
    '109.248.204.92',
    '109.248.205.171',
    '109.248.205.179',
    '109.248.205.197',
    '109.248.205.48',
    '109.248.48.32',
    '109.248.54.100',
    '109.248.54.165',
    '109.248.54.173',
    '109.248.54.253',
    '109.248.55.16',
    '122.233.224.192',
    '122.235.194.85',
    '140.238.172.132',
    '154.16.243.187',
    '162.55.230.167',
    '176.31.2.4',
    '176.31.2.5',
    '176.31.2.6',
    '176.31.2.7',
    '176.31.80.141',
    '176.31.80.143',
    '178.33.176.192',
    '178.33.176.193',
    '178.33.176.194',
    '178.33.176.195',
    '178.33.176.200',
    '178.33.176.201',
    '178.33.176.202',
    '178.33.176.203',
    '183.93.70.31',
    '185.128.27.190',
    '185.181.244.161',
    '185.181.244.232',
    '185.181.245.170',
    '185.181.247.126',
    '185.181.247.232',
    '185.181.247.233',
    '185.181.247.75',
    '188.130.128.119',
    '188.130.128.123',
    '188.130.128.171',
    '188.130.128.185',
    '188.130.128.187',
    '188.130.128.202',
    '188.130.128.237',
    '188.130.128.44',
    '188.130.129.114',
    '188.130.129.233',
    '188.130.129.247',
    '188.130.129.86',
    '188.130.129.92',
    '188.130.136.67',
    '188.130.137.112',
    '188.130.137.182',
    '188.130.142.101',
    '188.130.142.41',
    '188.130.143.123',
    '188.130.143.59',
    '188.130.143.75',
    '188.130.184.109',
    '188.130.184.183',
    '188.130.184.207',
    '188.130.185.180',
    '188.130.187.129',
    '188.130.187.224',
    '188.130.188.142',
    '188.130.188.246',
    '188.130.189.131',
    '188.130.189.193',
    '188.130.189.45',
    '188.130.210.191',
    '188.130.210.87',
    '188.130.211.39',
    '188.130.218.232',
    '188.130.219.120',
    '188.130.219.14',
    '188.130.220.113',
    '188.130.220.90',
    '188.130.221.157',
    '188.130.221.2',
    '188.130.221.25',
    '188.130.221.8',
    '188.130.221.99',
    '188.165.0.223',
    '192.241.112.145',
    '192.241.112.9',
    '193.53.168.179',
    '193.58.168.22',
    '193.58.169.108',
    '193.58.169.127',
    '194.156.123.178',
    '194.32.237.27',
    '194.34.248.138:',
    '194.34.248.254',
    '194.34.248.46',
    '194.34.248.62',
    '194.35.113.158',
    '194.35.113.26',
    '194.35.113.29',
    '194.5.9.20',
    '196.19.178.110',
    '2.59.50.141',
    '209.198.8.138',
    '209.198.8.139',
    '212.115.49.130',
    '212.115.49.9',
    '213.226.101.137',
    '213.226.101.228',
    '213.32.119.0',
    '213.32.119.1',
    '213.32.119.10',
    '213.32.119.11',
    '213.32.119.12',
    '213.32.119.13',
    '213.32.119.14',
    '213.32.119.15',
    '213.32.119.2',
    '213.32.119.3',
    '213.32.119.4',
    '213.32.119.5',
    '213.32.119.6',
    '213.32.119.7',
    '213.32.119.8',
    '213.32.119.9',
    '31.40.203.202',
    '31.40.203.242',
    '31.40.203.93',
    '35.84.41.175',
    '37.59.172.236',
    '37.59.172.237',
    '37.59.172.238',
    '37.59.172.239',
    '45.11.1.106',
    '45.11.20.100',
    '45.11.20.14',
    '45.11.20.144',
    '45.11.20.53',
    '45.11.20.85',
    '45.11.21.158',
    '45.11.21.162',
    '45.11.21.44',
    '45.130.127.221',
    '45.134.182.74',
    '45.134.183.247',
    '45.134.252.124',
    '45.135.33.101',
    '45.139.176.105',
    '45.139.177.164',
    '45.139.177.57',
    '45.140.52.189'
    '45.140.52.189',
    '45.140.53.132',
    '45.140.55.120',
    '45.142.253.217',
    '45.144.36.210',
    '45.144.36.242',
    '45.145.119.100',
    '45.147.193.220',
    '45.15.72.115',
    '45.15.72.163',
    '45.15.73.148',
    '45.15.73.189',
    '45.15.73.57',
    '45.151.145.18',
    '45.151.145.198',
    '45.151.145.215',
    '45.61.118.12',
    '45.81.137.194',
    '45.81.137.40',
    '45.84.176.163',
    '45.84.176.171',
    '45.84.176.60',
    '45.86.0.8',
    '45.86.1.172',
    '45.86.1.237',
    '45.87.243.183',
    '45.87.252.146',
    '45.87.252.197',
    '45.87.253.229',
    '45.87.253.82',
    '45.90.196.107',
    '45.90.196.134',
    '45.90.196.146',
    '45.90.196.4',
    '46.8.10.53',
    '46.8.106.139',
    '46.8.106.3',
    '46.8.11.162',
    '46.8.11.180',
    '46.8.11.57',
    '46.8.110.213',
    '46.8.110.52',
    '46.8.110.69',
    '46.8.111.157',
    '46.8.111.18',
    '46.8.111.19',
    '46.8.111.235',
    '46.8.111.80',
    '46.8.14.149',
    '46.8.14.38',
    '46.8.14.43',
    '46.8.15.214',
    '46.8.15.4',
    '46.8.154.166',
    '46.8.154.196',
    '46.8.154.221',
    '46.8.154.54',
    '46.8.156.183',
    '46.8.156.4',
    '46.8.157.12',
    '46.8.157.206',
    '46.8.157.243',
    '46.8.16.105',
    '46.8.16.252',
    '46.8.17.12',
    '46.8.17.191',
    '46.8.17.214',
    '46.8.192.18',
    '46.8.192.30',
    '46.8.192.60',
    '46.8.192.88',
    '46.8.193.205',
    '46.8.193.215',
    '46.8.212.70',
    '46.8.213.139',
    '46.8.213.219',
    '46.8.22.148',
    '46.8.22.57',
    '46.8.22.59',
    '46.8.222.131',
    '46.8.222.220',
    '46.8.222.82',
    '46.8.223.114',
    '46.8.223.126',
    '46.8.223.181',
    '46.8.223.36',
    '46.8.223.48',
    '46.8.23.120',
    '46.8.23.218',
    '46.8.23.224',
    '46.8.23.248',
    '46.8.23.57',
    '46.8.23.68',
    '46.8.56.253',
    '46.8.57.217',
    '5.196.255.100',
    '5.196.255.101',
    '5.196.255.102',
    '5.196.255.103',
    '5.196.83.234',
    '58.97.160.13',
    '77.83.148.181',
    '77.83.148.192',
    '77.83.148.48',
    '77.94.1.139',
    '77.94.1.38',
    '78.33.176.200',
    '79.11.85.104',
    '80.117.11.84',
    '81.163.126.13',
    '84.54.53.48',
    '87.148.7.210',
    '94.130.133.115',
    '94.158.190.37',
    '94.158.190.9',
    '94.23.171.134',
    '95.182.125.228',
    '95.182.125.94',
    '95.182.126.21',
    '95.182.126.210',
    '95.182.126.54',
    '95.182.127.194',
    '95.182.127.52',
]

# query_block_list = re.compile(
#     r'('
#     + r"site:zhidao\.baidu\.com .*"
#     + r')'
# )

def is_accepted_request() -> bool:
    # pylint: disable=too-many-return-statements
    redis_client = redisdb.client()
    user_agent = request.headers.get('User-Agent', 'unknown')
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')

    if request.path == '/healthz':
        return True

    if x_forwarded_for in ip_block_list:
        logger.debug("BLOCK %s: %s --> IP is on block list: %s" % (x_forwarded_for, request.path, user_agent))
        return False

    # q = request.form.get('q')
    # if q and query_block_list.match(q):
    #     logger.debug("BLOCK %s: %s --> query is on block list: %s" % (x_forwarded_for, request.path, q))
    #     return False

    if block_user_agent.match(user_agent):
        logger.debug("BLOCK %s: %s --> detected User-Agent: %s" % (x_forwarded_for, request.path, user_agent))
        return False

    if request.path == '/search':

        c_burst = incr_sliding_window(redis_client, 'IP limit, burst' + x_forwarded_for, 20)
        c_10min = incr_sliding_window(redis_client, 'IP limit, 10 minutes' + x_forwarded_for, 600)
        if c_burst > 15 or c_10min > 150:
            logger.debug("BLOCK %s: to many request", x_forwarded_for)
            return False

        if len(request.headers.get('Accept-Language', '').strip()) == '':
            logger.debug("BLOCK %s: missing Accept-Language", x_forwarded_for)
            return False

        if request.headers.get('Connection') == 'close':
            logger.debug("BLOCK %s: got Connection=close", x_forwarded_for)
            return False

        accept_encoding_list = [l.strip() for l in request.headers.get('Accept-Encoding', '').split(',')]
        if 'gzip' not in accept_encoding_list and 'deflate' not in accept_encoding_list:
            logger.debug("BLOCK %s: suspicious Accept-Encoding", x_forwarded_for)
            return False

        if 'text/html' not in request.accept_mimetypes:
            logger.debug("BLOCK %s: Accept-Encoding misses text/html", x_forwarded_for)
            return False

        if request.args.get('format', 'html') != 'html':
            c = incr_sliding_window(redis_client, 'API limit' + x_forwarded_for, 3600)
            if c > 4:
                logger.debug("BLOCK %s: API limit exceeded", x_forwarded_for)
                return False

    logger.debug(
        "OK %s: '%s'" % (x_forwarded_for, request.path)
        + " || form: %s" % request.form
        + " || Accept: %s" % request.headers.get('Accept', '')
        + " || Accept-Language: %s" % request.headers.get('Accept-Language', '')
        + " || Accept-Encoding: %s" % request.headers.get('Accept-Encoding', '')
        + " || Content-Type: %s" % request.headers.get('Content-Type', '')
        + " || Content-Length: %s" % request.headers.get('Content-Length', '')
        + " || Connection: %s" % request.headers.get('Connection', '')
        + " || User-Agent: %s" % user_agent
    )

    return True


def pre_request():
    if not is_accepted_request():
        return 'Too Many Requests', 429
    return None


def init(app, settings):
    if not settings['server']['limiter']:
        return False

    if not redisdb.client():
        logger.error("The limiter requires Redis")  # pylint: disable=undefined-variable
        return False

    app.before_request(pre_request)
    return True
