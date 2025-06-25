import os
import requests
from requests.adapters import HTTPAdapter, Retry
import json
import urllib
#from urllib.parse import urlparse
try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse
import re, uuid
from time import time
from time import sleep
from datetime import datetime, timedelta
import math
from urllib.request import urlopen
import base64
import logging

logger = None

s = requests.Session()
retries = Retry(total=3, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
s.mount("http://", HTTPAdapter(max_retries=retries))
#defaultUserAgent = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
defaultUserAgent = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3"
defaultModel = "MAG254"
defaultSerialNumber = "0000000000000"
defaultTimezone = "America/Toronto"

def set_logger(loggerinstance):
    if loggerinstance:
        global logger
        logger = loggerinstance


def is_json(myjson):
  #try:
  #  json_object = json.loads(myjson)
  #except ValueError, e:
  #  return False
  json_object = json.loads(myjson)
  return True

def getUrl(url, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    def parseResponse(url, data):
        java = data.text.replace(" ", "").replace("'", "").replace("+", "")
        pattern = re.search(r"varpattern.*\/(\(http.*)\/;", java).group(1)
        result = re.search(pattern, url)
        protocolIndex = re.search(r"this\.portal_protocol.*(\d).*;", java).group(1)
        ipIndex = re.search(r"this\.portal_ip.*(\d).*;", java).group(1)
        pathIndex = re.search(r"this\.portal_path.*(\d).*;", java).group(1)
        protocol = result.group(int(protocolIndex))
        ip = result.group(int(ipIndex))
        path = result.group(int(pathIndex))
        portalPatern = re.search(r"this\.ajax_loader=(.*\.php);", java).group(1)
        portal = (
            portalPatern.replace("this.portal_protocol", protocol)
            .replace("this.portal_ip", ip)
            .replace("this.portal_path", path)
        )
        return portal

    url = urlparse(url).scheme + "://" + urlparse(url).netloc
    urls = [
        "/c/xpcom.common.js",
        "/client/xpcom.common.js",
        "/c_/xpcom.common.js",
        "/stalker_portal/c/xpcom.common.js",
        "/stalker_portal/c_/xpcom.common.js",
    ]

    proxies = {"http": proxy, "https": proxy}
    #headers = {"User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)"}
    headers = {"User-Agent": useragent}

    try:
        for i in urls:
            try:
                response = s.get(url + i, headers=headers, proxies=proxies)
            except:
                response = None
            if response:
                return parseResponse(url + i, response)
    except:
        pass

    # sometimes these pages dont like proxies!
    try:
        for i in urls:
            try:
                response = s.get(url + i, headers=headers)
            except:
                response = None
            if response:
                return parseResponse(url + i, response)
    except:
        pass


def getToken(url, mac, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {"User-Agent": useragent}
    try:
        response = s.get(
            url + "?type=stb&action=handshake&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        token = response.json()["js"]["token"]
        if token:
            return token
    except:
        pass


def getProfile(url, mac, token, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent,
        "Authorization": "Bearer " + token,
    }
    try:
        response = s.get(
            url + "?type=stb&action=get_profile&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        profile = response.json()["js"]
        if profile:
            return profile
    except:
        pass


def getExpires(url, mac, token, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent,
        "Authorization": "Bearer " + token,
    }
    try:
        response = s.get(
            url + "?type=account_info&action=get_main_info&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        expires = response.json()["js"]["phone"]
        if expires:
            return expires
    except:
        pass


def getAllChannels(url, mac, token, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent,
        "Authorization": "Bearer " + token,
    }
    try:
        response = s.get(
            url
            + "?type=itv&action=get_all_channels&force_ch_link_check=&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        channels = response.json()["js"]["data"]
        if channels:
            return channels
    except:
        pass


def getGenres(url, mac, token, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent,
        "Authorization": "Bearer " + token,
    }
    try:
        response = s.get(
            url + "?action=get_genres&type=itv&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        genreData = response.json()["js"]
        if genreData:
            return genreData
    except:
        pass


def getGenreNames(url, mac, token, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    try:
        genreData = getGenres(url, mac, token, proxy, useragent)
        genres = {}
        for i in genreData:
            gid = i["id"]
            name = i["title"]
            genres[gid] = name
        if genres:
            return genres
    except:
        pass


def getLink(url, mac, token, cmd, proxy=None, useragent=None):

    if useragent is None:
        useragent = defaultUserAgent


    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent,
        "Authorization": "Bearer " + token,
    }
    try:
        response = s.get(
            url
            + "?type=itv&action=create_link&cmd="
            + cmd
            + "&series=0&forced_storage=false&disable_ad=false&download=false&force_ch_link_check=false&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        data = response.json()
        link = data["js"]["cmd"].split()[-1]
        if link:
            return link
    except:
        pass


def getEpg(url, mac, token, period, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent,
        "Authorization": "Bearer " + token,
    }
    try:
        response = s.get(
            url
            + "?type=itv&action=get_epg_info&period="
            + str(period)
            + "&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        data = response.json()["js"]["data"]
        if data:
            return data
    except:
        pass

def watchdogUpdate(url, mac, token, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent,
        "Authorization": "Bearer " + token,
    }
    try:

        response = s.get(
            url
            + "action=get_events&event_active_id=0&init=0&type=watchdog&cur_play_type=1&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        #data = response.json()["js"]["data"]
        data = response.text
        if data:
            return data
    except Exception as e:
        logger.error("stb.watchdogUpdate() Error: {}".format(e))
        pass


def getEpgSDT(url, mac, token, ch_id, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent,
        "Authorization": "Bearer " + token,
    }
    try:
        now = datetime.today() - timedelta(days=1)

        response = s.get(
            url
            + "?type=epg"
            + "&action=get_simple_data_table"
            + "&ch_id=" + str(ch_id)
            + "&date=" + str(now.strftime("%Y-%m-%d"))
            + "&p=0"
            + "&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        data = response.json()["js"]["data"]
        if data:
            return data
    except:
        pass

def getShortEpg(url, mac, token, ch_id, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent,
        "Authorization": "Bearer " + token,
    }
    try:
        #now = datetime.today() - timedelta(days=1)
        response = s.get(
            url
            + "?type=itv"
            + "&action=get_short_epg"
            + "&ch_id=" + str(ch_id)
            + "&size=10&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        data = response.json()["js"]
        if data:
            return data
    except  Exception as e:
        logger.error("stb.getShortEpg() Error: {}".format(e))
        pass


def getlocalization(url, proxy=None, useragent=None):
    if useragent is None:
        useragent = defaultUserAgent

    proxies = {"http": proxy, "https": proxy}
    #cookies = {"mac": mac, "stb_lang": "en", "timezone": "America/Toronto"}
    cookies = {"stb_lang": "en", "timezone": defaultTimezone}
    headers = {
        "User-Agent": useragent
    }
    try:
        response = s.get(
            url
            + "?type=stb&action=get_localization&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
        )
        data = response.json()["js"]["data"]
        if data:
            return data
    except:
        pass
