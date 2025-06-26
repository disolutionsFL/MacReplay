VERSION = "2.2.2"
import sys
import os
import shutil
import time
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import threading
from threading import Thread
import multiprocessing
from multiprocessing import Process, Queue
import logging
import copy
import base64
logger = logging.getLogger("MacReplay")
logger.setLevel(logging.INFO)
logFormat = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")


home_dir = os.path.expanduser("~")  # Get the user's home directory
log_dir = os.path.join(home_dir, "Evilvir.us")  # Subdirectory for logs
# Create the directory if it doesn't already exist
os.makedirs(log_dir, exist_ok=True)
# Full path to the log file
log_file_path = os.path.join(log_dir, "MacReplay.log")
# Set up the FileHandler
fileHandler = logging.FileHandler(log_file_path)
fileHandler.setFormatter(logFormat)



logger.addHandler(fileHandler)
consoleFormat = logging.Formatter("[%(levelname)s] %(message)s")
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(consoleFormat)
logger.addHandler(consoleHandler)


# Check if running as a PyInstaller executable
if getattr(sys, 'frozen', False):
    # If running as a PyInstaller executable, use _MEIPASS for the temp folder
    app_dir = sys._MEIPASS
else:
    # If running as a regular script, use the script's current directory
    app_dir = os.path.dirname(os.path.abspath(__file__))

# Paths to ffmpeg.exe and ffprobe.exe in the root folder
ffmpeg_path = os.path.join(app_dir, 'ffmpeg', 'ffmpeg.exe')
ffprobe_path = os.path.join(app_dir, 'ffmpeg', 'ffprobe.exe')

# Check if the files exist (for debugging purposes)
if not os.path.exists(ffmpeg_path) or not os.path.exists(ffprobe_path):
    logger.error("Error: ffmpeg.exe or ffprobe.exe not found!")
#else:
#    print(f"Found ffmpeg at {ffmpeg_path}")
#    print(f"Found ffprobe at {ffprobe_path}")

import flask
from flask import Flask, jsonify
import stb
import json
import re
import subprocess
import uuid
import xml.etree.cElementTree as ET
from flask import (
    Flask,
    render_template,
    redirect,
    request,
    Response,
    make_response,
    flash,
)
from datetime import datetime, timezone
from functools import wraps
import secrets
import waitress

app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)
basePath = os.path.abspath(os.getcwd())

if os.getenv("HOST"):
    host = os.getenv("HOST")
else:
    host = "127.0.0.1:8001"
logger.info(f"Server started on http://{host}")

# Get the base path for the user directory
basePath = os.path.expanduser("~")

# Determine the config file path, placing it in 'evilvir.us' subdirectory
if os.getenv("CONFIG"):
    configFile = os.getenv("CONFIG")
else:
    configFile = os.path.join(basePath, "evilvir.us", "MacReplay.json")

# Ensure the subdirectory exists
os.makedirs(os.path.dirname(configFile), exist_ok=True)

logger.info(f"Using config file: {configFile}")

occupied = {}
config = {}
cached_lineup = []
cached_playlist = None
last_playlist_host = None
cached_xmltv = None
last_updated = 0
stb.set_logger(logger)


d_ffmpegcmd = [
    "-re",                      # Flag for real-time streaming
    "-http_proxy", "<proxy>",   # Proxy setting
    "-timeout", "<timeout>",    # Timeout setting
    "-i", "<url>",              # Input URL
    "-map", "0",                # Map all streams
    "-codec", "copy",           # Copy codec (no re-encoding)
    "-f", "mpegts",             # Output format
    "-flush_packets", "0",      # Disable flushing packets (optimized for faster output)
    "-fflags", "+nobuffer",     # No buffering for low latency
    "-flags", "low_delay",      # Low delay flag
    "-strict", "experimental",  # Use experimental features
    "-analyzeduration", "0",    # Skip analysis duration for faster startup
    "-probesize", "32",         # Set probe size to reduce input analysis time
    "-copyts",                  # Copy timestamps (avoid recalculating)
    "-threads", "12",           # Enable multi-threading (adjust thread count as needed)
    "pipe:"                     # Output to pipe
]







defaultSettings = {
    "stream method": "ffmpeg",
    "ffmpeg command": "-re -http_proxy <proxy> -timeout <timeout> -i <url> <headers> -map 0 -codec copy -f mpegts -flush_packets 0 -fflags +nobuffer -flags low_delay -strict experimental -analyzeduration 0 -probesize 32 -copyts -threads 12 pipe:",
    "ffmpeg timeout": "5",
    "cache expiryhrs": "24",
    "cache disabledelete": "false",
    "test streams": "true",
    "try all macs": "true",
    "use channel genres": "true",
    "use channel numbers": "true",
    "sort playlist by channel genre": "false",
    "sort playlist by channel number": "true",
    "sort playlist by channel name": "false",
    "enable security": "false",
    "username": "admin",
    "password": "12345",
    "enable hdhr": "true",
    "hdhr name": "MacReplay",
    "hdhr id": str(uuid.uuid4().hex),
    "hdhr tuners": "10",
    "ka interval": "2",
}

defaultPortal = {
    "enabled": "true",
    "name": "",
    "url": "",
    "macs": {},
    "prioritymacs": {},
    "streams per mac": "1",
    "epg offset": "0",
    "proxy": "",
    "useragent": "",
    "kaenabled": "true",
    "enabled channels": [],
    "custom channel names": {},
    "custom channel numbers": {},
    "custom genres": {},
    "custom epg ids": {},
    "fallback channels": {},
}


def loadConfig():
    try:
        with open(configFile) as f:
            data = json.load(f)
    except:
        logger.warning("No existing config found. Creating a new one")
        data = {}

    data.setdefault("portals", {})
    data.setdefault("settings", {})

    settings = data["settings"]
    settingsOut = {}

    for setting, default in defaultSettings.items():
        value = settings.get(setting)
        if not value or type(default) != type(value):
            value = default
        settingsOut[setting] = value

    data["settings"] = settingsOut

    portals = data["portals"]
    portalsOut = {}

    for portal in portals:
        portalsOut[portal] = {}
        for setting, default in defaultPortal.items():
            value = portals[portal].get(setting)
            if not value or type(default) != type(value):
                value = default
            portalsOut[portal][setting] = value

    data["portals"] = portalsOut

    with open(configFile, "w") as f:
        json.dump(data, f, indent=4)

    return data

def is_file_older_than (file, delta):
    cutoff = datetime.utcnow() - delta
    mtime = datetime.utcfromtimestamp(os.path.getmtime(file))
    if mtime < cutoff:
        return True
    return False

def getPortals():
    return config["portals"]


def savePortals(portals):
    with open(configFile, "w") as f:
        config["portals"] = portals
        json.dump(config, f, indent=4)

def savePortalCache(portal, mac=None, profile=None, channels=None, genres=None):
    portalprofile = ""
    portalchannels = ""
    portalgenres = ""
    portalname = ""

    portalcachepath = os.path.join(basePath, "evilvir.us", "portalcache")
    os.makedirs(portalcachepath, exist_ok=True)

    if portal:
        portalname = portal["name"]
    else:
        return

    if profile:
        portalprofile = profile
        portalprofiledatafilename = portalname.replace(" ", "_")
        portalprofiledatafilename = portalprofiledatafilename.replace("'", "")
        portalprofiledatafilename = portalprofiledatafilename.replace("\"", "")
        portalprofiledatafilename = portalprofiledatafilename.replace(",", "_")

        if mac is None:
            portalprofilepatafilepath = os.path.join(portalcachepath, "{}_profile.json".format(portalprofiledatafilename))
        else:
            mac = mac.replace(" ", "")
            mac = mac.replace(":", "")
            portalprofilepatafilepath = os.path.join(portalcachepath, "{}_{}_profile.json".format(portalprofiledatafilename, mac))

        with open(portalprofilepatafilepath, "w") as f:
            json.dump(portalprofile, f, indent=4)

    if channels:
        portalchannels = channels
        portalchannelsdatafilename = portalname.replace(" ", "_")
        portalchannelsdatafilename = portalchannelsdatafilename.replace("'", "")
        portalchannelsdatafilename = portalchannelsdatafilename.replace("\"", "")
        portalchannelsdatafilename = portalchannelsdatafilename.replace(",", "_")

        if mac is None:
            portalchannelsdatafilepath = os.path.join(portalcachepath, "{}_channels.json".format(portalchannelsdatafilename))
        else:
            mac = mac.replace(" ", "")
            mac = mac.replace(":", "")
            portalchannelsdatafilepath = os.path.join(portalcachepath, "{}_{}_channels.json".format(portalchannelsdatafilename, mac))

        with open(portalchannelsdatafilepath, "w") as f:
            json.dump(portalchannels, f, indent=4)

    if genres:
        portalgenres = genres
        portalgenresdatafilename = portalname.replace(" ", "_")
        portalgenresdatafilename = portalgenresdatafilename.replace("'", "")
        portalgenresdatafilename = portalgenresdatafilename.replace("\"", "")
        portalgenresdatafilename = portalgenresdatafilename.replace(",", "_")

        if mac is None:
            portalgenresdatafilepath = os.path.join(portalcachepath, "{}_genres.json".format(portalgenresdatafilename))
        else:
            mac = mac.replace(" ", "")
            mac = mac.replace(":", "")
            portalgenresdatafilepath = os.path.join(portalcachepath, "{}_{}_genres.json".format(portalgenresdatafilename, mac))

        with open(portalgenresdatafilepath, "w") as f:
            json.dump(portalgenres, f, indent=4)


def saveCombinedPortalChannelsCache(portal, channels=None, genres=None):
    portalchannels = ""
    portalgenres = ""
    portalname = ""

    portalcachepath = os.path.join(basePath, "evilvir.us", "portalcache")
    os.makedirs(portalcachepath, exist_ok=True)

    if portal:
        portalname = portal["name"]
    else:
        return

    if channels:
        portalchannels = channels
        portalchannelsdatafilename = portalname.replace(" ", "_")
        portalchannelsdatafilename = portalchannelsdatafilename.replace("'", "")
        portalchannelsdatafilename = portalchannelsdatafilename.replace("\"", "")
        portalchannelsdatafilename = portalchannelsdatafilename.replace(",", "_")

        portalchannelsdatafilepath = os.path.join(portalcachepath, "{}_combined_portalchannels.json".format(portalchannelsdatafilename))

        with open(portalchannelsdatafilepath, "w") as f:
            json.dump(portalchannels, f, indent=4)

    if genres:
        portalgenres = genres
        portalgenresdatafilename = portalname.replace(" ", "_")
        portalgenresdatafilename = portalgenresdatafilename.replace("'", "")
        portalgenresdatafilename = portalgenresdatafilename.replace("\"", "")
        portalgenresdatafilename = portalgenresdatafilename.replace(",", "_")

        portalgenresdatafilepath = os.path.join(portalcachepath, "{}_combined_portalgenres.json".format(portalgenresdatafilename))

        with open(portalgenresdatafilepath, "w") as f:
            json.dump(portalgenres, f, indent=4)


def getCombinedPortalChannelsCache(portal):
    portalname = ""
    data = []
    cachetimeouthrs = int(getSettings()["cache expiryhrs"])
    purgeCache = getSettings().get("cache disabledelete", "false") == "false"

    if portal:
        portalname = portal["name"]
    else:
        return []

    try:
        portalcachepath = os.path.join(basePath, "evilvir.us", "portalcache")
        os.makedirs(portalcachepath, exist_ok=True)

        portalchannelsdatafilename = portalname.replace(" ", "_")
        portalchannelsdatafilename = portalchannelsdatafilename.replace("'", "")
        portalchannelsdatafilename = portalchannelsdatafilename.replace("\"", "")
        portalchannelsdatafilename = portalchannelsdatafilename.replace(",", "_")

        filename = "{}_combined_portalchannels.json".format(portalchannelsdatafilename)
        portalchannelsdatafilepath = os.path.join(portalcachepath, filename)

        if not os.path.exists(portalchannelsdatafilepath):
            return []

        if is_file_older_than(portalchannelsdatafilepath, timedelta(hours=cachetimeouthrs)):
            if purgeCache:
                os.remove(portalchannelsdatafilepath)
                logger.warning("Cache file ({}) deleted due to age".format(filename))
                return []

        with open(portalchannelsdatafilepath, 'r') as file:
            data = json.load(file)
    except Exception as ex:
        logger.warning("Error retrieving Combined Portal channel cache: {}".format(ex))
        data = []

    return data


def getPortalChannelsCache(portal, mac):
    portalname = ""
    data = None
    cachetimeouthrs = int(getSettings()["cache expiryhrs"])
    purgeCache = getSettings().get("cache disabledelete", "false") == "false"

    if portal:
        portalname = portal["name"]
    else:
        return None

    if mac is None:
        return None

    try:
        portalcachepath = os.path.join(basePath, "evilvir.us", "portalcache")
        os.makedirs(portalcachepath, exist_ok=True)

        mac = mac.replace(" ", "")
        mac = mac.replace(":", "")
        portalchannelsdatafilename = portalname.replace(" ", "_")
        portalchannelsdatafilename = portalchannelsdatafilename.replace("'", "")
        portalchannelsdatafilename = portalchannelsdatafilename.replace("\"", "")
        portalchannelsdatafilename = portalchannelsdatafilename.replace(",", "_")

        filename = "{}_{}_channels.json".format(portalchannelsdatafilename, mac)
        portalchannelsdatafilepath = os.path.join(portalcachepath, filename)

        if not os.path.exists(portalchannelsdatafilepath):
            return None

        if is_file_older_than(portalchannelsdatafilepath, timedelta(hours=cachetimeouthrs)):
            if purgeCache:
                os.remove(portalchannelsdatafilepath)
                logger.warning("Cache file ({}) deleted due to age".format(filename))
                return None

        with open(portalchannelsdatafilepath, 'r') as file:
            data = json.load(file)
    except Exception as ex:
        logger.warning("Error retrieving Portal channel cache: {}".format(ex))
        data = None

    return data


def getPortalGenresCache(portal, mac):
    portalname = ""
    data = None
    cachetimeouthrs = int(getSettings()["cache expiryhrs"])
    purgeCache = getSettings().get("cache disabledelete", "false") == "false"


    if portal:
        portalname = portal["name"]
    else:
        return None

    if mac is None:
        return None

    try:
        portalcachepath = os.path.join(basePath, "evilvir.us", "portalcache")
        os.makedirs(portalcachepath, exist_ok=True)

        mac = mac.replace(" ", "")
        mac = mac.replace(":", "")
        portalgenresdatafilename = portalname.replace(" ", "_")
        portalgenresdatafilename = portalgenresdatafilename.replace("'", "")
        portalgenresdatafilename = portalgenresdatafilename.replace("\"", "")
        portalgenresdatafilename = portalgenresdatafilename.replace(",", "_")

        filename = "{}_{}_genres.json".format(portalgenresdatafilename, mac)
        portalgenresdatafilepath = os.path.join(portalcachepath, filename)

        if not os.path.exists(portalgenresdatafilepath):
            return None

        if is_file_older_than(portalgenresdatafilepath, timedelta(hours=cachetimeouthrs)):
            if purgeCache:
                os.remove(portalgenresdatafilepath)
                logger.warning("Cache file ({}) deleted due to age".format(filename))
                return None

        with open(portalgenresdatafilepath) as file:
            data = json.load(file)

    except Exception as ex:
        logger.warning("Error retrieving Portal genres cache: {}".format(ex))
        data = None

    return data

def getCombinedPortalGenresCache(portal):
    portalname = ""
    data = []
    cachetimeouthrs = int(getSettings()["cache expiryhrs"])
    purgeCache = getSettings().get("cache disabledelete", "false") == "false"

    if portal:
        portalname = portal["name"]
    else:
        return []

    try:
        portalcachepath = os.path.join(basePath, "evilvir.us", "portalcache")
        os.makedirs(portalcachepath, exist_ok=True)

        portalgenresdatafilename = portalname.replace(" ", "_")
        portalgenresdatafilename = portalgenresdatafilename.replace("'", "")
        portalgenresdatafilename = portalgenresdatafilename.replace("\"", "")
        portalgenresdatafilename = portalgenresdatafilename.replace(",", "_")

        filename = "{}_combined_portalgenres.json".format(portalgenresdatafilename)
        portalgenresdatafilepath = os.path.join(portalcachepath, filename)

        if not os.path.exists(portalgenresdatafilepath):
            return []

        if is_file_older_than(portalgenresdatafilepath, timedelta(hours=cachetimeouthrs)):
            if purgeCache:
                os.remove(portalgenresdatafilepath)
                logger.warning("Cache file ({}) deleted due to age".format(filename))
                return []

        with open(portalgenresdatafilepath) as file:
            data = json.load(file)

    except Exception as ex:
        logger.warning("Error retrieving Combined Portal genres cache: {}".format(ex))
        data = []

    return data



def getSettings():
    return config["settings"]


def saveSettings(settings):
    with open(configFile, "w") as f:
        config["settings"] = settings
        json.dump(config, f, indent=4)


def authorise(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        settings = getSettings()
        security = settings["enable security"]
        username = settings["username"]
        password = settings["password"]
        if (
            security == "false"
            or auth
            and auth.username == username
            and auth.password == password
        ):
            return f(*args, **kwargs)

        return make_response(
            "Could not verify your login!",
            401,
            {"WWW-Authenticate": 'Basic realm="Login Required"'},
        )

    return decorated


def moveMac(portalId, mac):
    portals = getPortals()
    macs = portals[portalId]["macs"]
    x = macs[mac]
    del macs[mac]
    macs[mac] = x
    portals[portalId]["macs"] = macs
    savePortals(portals)

def keepalive_watchdog():

    if occupied is None or len(occupied) == 0:
        return ""
    else:
        if occupied is not None:
            count = 0
            portalId = ""
            for i in occupied:
                portalId = i
                for p in occupied.get(portalId, []):
                    count = count + 1

                    if p["portalId"] != "" and p["mac"] != "":

                        portal = getPortals().get(portalId)
                        if portal:
                            portalName = portal.get("name")
                            url = portal.get("url")
                            mac = p["mac"]
                            proxy = portal.get("proxy")
                            useragent = portal.get("useragent")
                            kaenabled = portal.get("kaenabled")

                            if kaenabled and kaenabled == "true":
                                token = stb.getToken(url, mac, proxy, useragent)
                                logger.info("Sending Keep-Alive to portal({}), mac({})".format(portalName, mac))
                                watchdogresp = stb.watchdogUpdate(url, mac, token, proxy, useragent)
                                if watchdogresp == "\n":
                                    watchdogresp = ""
                                return "{}".format(watchdogresp)
                            else:
                                #keep-alive not enabled for portal
                                return ""
                        else:
                            return ""
                    else:
                        return ""
        return ""


@app.route("/", methods=["GET"])
@authorise
def home():
    return redirect("/portals", code=302)


@app.route("/webplayer", methods=["GET"])
@authorise
def webplayer():
    return render_template("webplayer.html", portals=getPortals())


@app.route("/portals", methods=["GET"])
@authorise
def portals():
    return render_template("portals.html", portals=getPortals())


@app.route("/portal/add", methods=["POST"])
@authorise
def portalsAdd():
    global cached_xmltv
    cached_xmltv = None
    id = uuid.uuid4().hex
    enabled = "true"
    name = request.form["name"]
    url = request.form["url"]
    macs = list(set(request.form["macs"].split(",")))
    prioritymacs = list(set(request.form["prioritymacs"].split(",")))
    streamsPerMac = request.form["streams per mac"]
    epgOffset = request.form["epg offset"]
    proxy = request.form["proxy"]
    useragent = request.form["useragent"]
    kaenabled = "true"
    profiledata = []

    if not url.endswith(".php"):
        url = stb.getUrl(url, proxy, useragent)
        if not url:
            logger.error("Error getting URL for Portal({})".format(name))
            flash("Error getting URL for Portal({})".format(name), "danger")
            return redirect("/portals", code=302)

    prioritymacsd = {}
    macsd = {}

    for mac in prioritymacs:
        token = stb.getToken(url, mac, proxy, useragent)
        if token:
            macprofiledata = stb.getProfile(url, mac, token, proxy, useragent)
            if macprofiledata:
                macprofiledata["mac"] = mac
                profiledata.append(macprofiledata)

            expiry = stb.getExpires(url, mac, token, proxy, useragent)
            if expiry:
                prioritymacsd[mac] = expiry
                logger.info(
                    "Successfully tested PRIORITY MAC({}) for Portal({})".format(mac, name)
                )
                flash(
                    "Successfully tested PRIORITY MAC({}) for Portal({})".format(mac, name),
                    "success",
                )
                continue

        logger.error("Error testing PRIORITY MAC({}) for Portal({})".format(mac, name))
        flash("Error testing PRIORITY MAC({}) for Portal({})".format(mac, name), "danger")


    for mac in macs:
        token = stb.getToken(url, mac, proxy, useragent)
        if token:
            macprofiledata = stb.getProfile(url, mac, token, proxy, useragent)
            if macprofiledata:
                macprofiledata["mac"] = mac
                profiledata.append(macprofiledata)

            expiry = stb.getExpires(url, mac, token, proxy, useragent)
            if expiry:
                macsd[mac] = expiry
                logger.info(
                    "Successfully tested MAC({}) for Portal({})".format(mac, name)
                )
                flash(
                    "Successfully tested MAC({}) for Portal({})".format(mac, name),
                    "success",
                )
                continue

        logger.error("Error testing MAC({}) for Portal({})".format(mac, name))
        flash("Error testing MAC({}) for Portal({})".format(mac, name), "danger")

    if len(prioritymacsd) > 0 or len(macsd) > 0:
        portal = {
            "enabled": enabled,
            "name": name,
            "url": url,
            "macs": macsd,
            "prioritymacs": prioritymacsd,
            "streams per mac": streamsPerMac,
            "epg offset": epgOffset,
            "proxy": proxy,
            "useragent": useragent,
            "kaenabled": kaenabled
        }

        for setting, default in defaultPortal.items():
            if not portal.get(setting):
                portal[setting] = default

        portals = getPortals()
        portals[id] = portal
        savePortals(portals)
        logger.info("Portal({}) added!".format(portal["name"]))

        if profiledata:
            savePortalCache(portal, None, profiledata, None, None)
            logger.info("Portal({}) profile saved!".format(portal["name"]))

    else:
        logger.error(
            "None of the MACs tested OK for Portal({}). Adding not successfull".format(
                name
            )
        )

    return redirect("/portals", code=302)


@app.route("/portal/update", methods=["POST"])
@authorise
def portalUpdate():
    global cached_xmltv
    cached_xmltv = None
    id = request.form["id"]
    enabled = request.form.get("enabled", "false")
    name = request.form["name"]
    url = request.form["url"]
    newmacs = list(set(request.form["macs"].split(",")))
    newprioritymacs = list(set(request.form["prioritymacs"].split(",")))
    streamsPerMac = request.form["streams per mac"]
    epgOffset = request.form["epg offset"]
    proxy = request.form["proxy"]
    useragent = request.form["useragent"]
    kaenabled = request.form.get("kaenabled", "false")
    retest = request.form.get("retest", None)
    profiledata = []

    if not url.endswith(".php"):
        url = stb.getUrl(url, proxy, useragent)
        if not url:
            logger.error("Error getting URL for Portal({})".format(name))
            flash("Error getting URL for Portal({})".format(name), "danger")
            return redirect("/portals", code=302)

    portals = getPortals()

    oldprioritymacs = portals[id]["prioritymacs"]
    prioritymacsout = {}
    deadprioritymacs = []

    for prioritymac in newprioritymacs:
        if retest or prioritymac not in oldprioritymacs.keys():
            token = stb.getToken(url, prioritymac, proxy, useragent)
            if token:
                prioritymacprofiledata = stb.getProfile(url, prioritymac, token, proxy, useragent)
                if prioritymacprofiledata:
                    prioritymacprofiledata["mac"] = prioritymac
                    profiledata.append(prioritymacprofiledata)

                expiry = stb.getExpires(url, prioritymac, token, proxy, useragent)
                if expiry:
                    prioritymacsout[prioritymac] = expiry
                    logger.info(
                        "Successfully tested PRIORITY MAC({}) for Portal({})".format(prioritymac, name)
                    )
                    flash(
                        "Successfully tested PRIORITY MAC({}) for Portal({})".format(prioritymac, name),
                        "success",
                    )

            if prioritymac not in list(prioritymacsout.keys()):
                deadprioritymacs.append(prioritymac)

        if prioritymac in oldprioritymacs.keys() and prioritymac not in deadprioritymacs:
            prioritymacsout[prioritymac] = oldprioritymacs[prioritymac]

        if prioritymac not in prioritymacsout.keys():
            logger.error("Error testing PRIORITY MAC({}) for Portal({})".format(prioritymac, name))
            flash("Error testing PRIORITY MAC({}) for Portal({})".format(prioritymac, name), "danger")

    if len(prioritymacsout) > 0:
        portals[id]["prioritymacs"] = prioritymacsout
    else:
        #portals[id]["prioritymacs"] = {}
        logger.error(
            "None of the PRIORITY MACs tested OK for Portal({}). Adding not successfull".format(
                name
            )
        )

    oldmacs = portals[id]["macs"]
    macsout = {}
    deadmacs = []

    for mac in newmacs:
        if retest or mac not in oldmacs.keys():
            token = stb.getToken(url, mac, proxy, useragent)
            if token:
                macprofiledata = stb.getProfile(url, mac, token, proxy, useragent)
                if macprofiledata:
                    macprofiledata["mac"] = mac
                    profiledata.append(macprofiledata)

                expiry = stb.getExpires(url, mac, token, proxy, useragent)
                if expiry:
                    macsout[mac] = expiry
                    logger.info(
                        "Successfully tested MAC({}) for Portal({})".format(mac, name)
                    )
                    flash(
                        "Successfully tested MAC({}) for Portal({})".format(mac, name),
                        "success",
                    )

            if mac not in list(macsout.keys()):
                deadmacs.append(mac)

        if mac in oldmacs.keys() and mac not in deadmacs:
            macsout[mac] = oldmacs[mac]

        if mac not in macsout.keys():
            logger.error("Error testing MAC({}) for Portal({})".format(mac, name))
            flash("Error testing MAC({}) for Portal({})".format(mac, name), "danger")

    if len(macsout) > 0:
        portals[id]["macs"] = macsout
    else:
        #portals[id]["macs"] = {}
        logger.error(
            "None of the MACs tested OK for Portal({}). Adding not successfull".format(
                name
            )
        )

    #update portal regardless of mac status
    portals[id]["enabled"] = enabled
    portals[id]["name"] = name
    portals[id]["url"] = url
    portals[id]["streams per mac"] = streamsPerMac
    portals[id]["epg offset"] = epgOffset
    portals[id]["proxy"] = proxy
    portals[id]["useragent"] = useragent
    portals[id]["kaenabled"] = kaenabled
    savePortals(portals)
    logger.info("Portal({}) updated!".format(name))
    flash("Portal({}) updated!".format(name), "success")

    if profiledata:
        savePortalCache(portals[id], None, profiledata, None, None)
        logger.info("Portal({}) profile saved!".format(name))

    return redirect("/portals", code=302)


@app.route("/portal/remove", methods=["POST"])
@authorise
def portalRemove():
    id = request.form["deleteId"]
    portals = getPortals()
    name = portals[id]["name"]
    del portals[id]
    savePortals(portals)
    logger.info("Portal ({}) removed!".format(name))
    flash("Portal ({}) removed!".format(name), "success")
    return redirect("/portals", code=302)


@app.route("/editor", methods=["GET"])
@authorise
def editor():
    return render_template("editor.html")
    


@app.route("/editor_data", methods=["GET"])
@authorise
def editor_data():
    channels = []
    portals = getPortals()

    for portal in portals:
        portalchannels = []
        portalgenres = []
        logger.info(f"getting Data from {portal}")
        if portals[portal]["enabled"] == "true":
            portalName = portals[portal]["name"]
            url = portals[portal]["url"]
            macs = list(portals[portal]["macs"].keys())
            prioritymacs = list(portals[portal]["prioritymacs"].keys())
            proxy = portals[portal]["proxy"]
            useragent = portals[portal]["useragent"]
            enabledChannels = portals[portal].get("enabled channels", [])
            customChannelNames = portals[portal].get("custom channel names", {})
            customGenres = portals[portal].get("custom genres", {})
            customChannelNumbers = portals[portal].get("custom channel numbers", {})
            customEpgIds = portals[portal].get("custom epg ids", {})
            fallbackChannels = portals[portal].get("fallback channels", {})

            portalchannels = getCombinedPortalChannelsCache(portals[portal])
            portalgenres = getCombinedPortalGenresCache(portals[portal])

            macsforprocessing = macs

            if prioritymacs is not None and len(prioritymacs) > 0:
                macsforprocessing = prioritymacs
                logger.info("Using PRIORITY MAC's for Portal({})".format(portalName))


            if (portalchannels is None or len(portalchannels) == 0) or (portalgenres is None or len(portalgenres) == 0):
                for mac in macsforprocessing:
                    logger.info(f"Using mac: {mac}")

                    try:
                        #intialize vars
                        token = None
                        portalprofile = None
                        allchannels = None
                        genres = None
                        savetocache = False

                        #get cache data first to save round trips to server, and to prevent from getting banned
                        allchannels = getPortalChannelsCache(portals[portal], mac)
                        genres = getPortalGenresCache(portals[portal], mac)

                        if allchannels is None and genres is None:
                            savetocache = True

                        #if we were able to get channels and genres from cache, why call the server at all? No need to.
                        if allchannels is None or genres is None:
                            token = stb.getToken(url, mac, proxy, useragent)
                            portalprofile = stb.getProfile(url, mac, token, proxy, useragent)

                        if allchannels is None:
                            allchannels = stb.getAllChannels(url, mac, token, proxy, useragent)
                            #force genres to re-download since they are needed for new channel list
                            genres = None
                            savetocache = True
                        else:
                            logger.info("Portal({}) channels retrieved from cache".format(portalName))

                        if genres is None:
                            genres = stb.getGenreNames(url, mac, token, proxy, useragent)
                            savetocache = True
                        else:
                            logger.info("Portal({}) genres retrieved from cache".format(portalName))

                        if savetocache:
                            savePortalCache(portals[portal], mac, portalprofile, allchannels, genres)
                            logger.info("Portal({}) profile, channels and genre data saved!".format(portalName))

                        #if we have multiple macs for a portal, we need to combine channels into a distinct list so we don't have to deal with duplicates
                        if allchannels is not None:
                            logger.info("Portal({}), {} channels found for mac {}".format(portalName, len(allchannels), mac))
                            for c in allchannels:
                                exists = next((x for x in portalchannels if x['id'] == c['id']), None)
                                if exists is None:
                                    portalchannels.append(c)

                        #same for genres
                        if genres is not None:
                            logger.info("Portal({}), {} genres found for mac {}".format(portalName, len(genres), mac))
                            if portalgenres is not None and len(portalgenres) == 0:
                                portalgenres = copy.deepcopy(genres)
                            else:
                                #merge genres for this mac with those already found for this portal
                                portalgenres.update(genres)

                        #break was only allowing first mac's channels to download, whereas other macs could have other channel lists
                        #break

                    except Exception as ex:
                        logger.info("Portal({}), error getting channels and/or genres: {}".format(portalName, ex))
                        allchannels = None
                        genres = None

            else:
                #we retrieved from cache, set all channels so we can parse the combine list
                allchannels = portalchannels

            if allchannels and portalchannels and len(portalchannels) >= len(allchannels):
                logger.info(
                    "Portal({}), {} total channels found across all macs".format(portalName, len(portalchannels)))
                allchannels = portalchannels
                saveCombinedPortalChannelsCache(portals[portal], portalchannels, None)

            if portalgenres and len(portalgenres) >= 0:
                logger.info(
                    "Portal({}), {} total genres found across all macs".format(portalName, len(portalgenres)))
                genres = copy.deepcopy(portalgenres)
                saveCombinedPortalChannelsCache(portals[portal], None, portalgenres)

            if allchannels and genres:
                for channel in allchannels:
                    channelId = str(channel["id"])
                    channelName = str(channel["name"])
                    channelNumber = str(channel["number"])
                    xmltvid = str(channel["xmltv_id"])
                    genre = str(genres.get(str(channel["tv_genre_id"])))

                    if xmltvid is None or xmltvid == "":
                        xmltvid=channelId

                    if channelId in enabledChannels:
                        enabled = True
                    else:
                        enabled = False
                    customChannelNumber = customChannelNumbers.get(channelId)
                    if customChannelNumber == None:
                        customChannelNumber = ""
                    customChannelName = customChannelNames.get(channelId)
                    if customChannelName == None:
                        customChannelName = ""
                    customGenre = customGenres.get(channelId)
                    if customGenre == None:
                        customGenre = ""
                    customEpgId = customEpgIds.get(channelId)
                    if customEpgId == None:
                        #customEpgId = ""
                        customEpgId = "{}_{}".format(xmltvid, channelNumber)
                    fallbackChannel = fallbackChannels.get(channelId)
                    if fallbackChannel == None:
                        fallbackChannel = ""

                    channels.append(
                        {
                            "portal": portal,
                            "portalName": portalName,
                            "enabled": enabled,
                            "channelNumber": channelNumber,
                            "customChannelNumber": customChannelNumber,
                            "channelName": channelName,
                            "customChannelName": customChannelName,
                            "genre": genre,
                            "customGenre": customGenre,
                            "channelId": channelId,
                            "customEpgId": customEpgId,
                            "fallbackChannel": fallbackChannel,
                            "link": "http://"
                            + host
                            + "/play/"
                            + portal
                            + "/"
                            + channelId
                            + "?web=true",
                        }
                    )




            else:
                logger.error(
                    "Error getting channel data for {}, skipping".format(portalName)
                )
                flash(
                    "Error getting channel data for {}, skipping".format(portalName),
                    "danger",
                )

    data = {"data": channels}

    return flask.jsonify(data)


@app.route("/editor/save", methods=["POST"])
@authorise
def editorSave():
    global cached_xmltv
    #cached_xmltv = None # The tv guide will be updated next time its downloaded
    threading.Thread(target=refresh_xmltv, daemon=True).start() #Force update in a seperate thread
    last_playlist_host = None     # The playlist will be updated next time it is downloaded
    Thread(target=refresh_lineup).start() # Update the channel lineup for plex.
    enabledEdits = json.loads(request.form["enabledEdits"])
    numberEdits = json.loads(request.form["numberEdits"])
    nameEdits = json.loads(request.form["nameEdits"])
    genreEdits = json.loads(request.form["genreEdits"])
    epgEdits = json.loads(request.form["epgEdits"])
    fallbackEdits = json.loads(request.form["fallbackEdits"])
    portals = getPortals()
    for edit in enabledEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        enabled = edit["enabled"]
        if enabled:
            portals[portal].setdefault("enabled channels", [])
            portals[portal]["enabled channels"].append(channelId)
        else:
            portals[portal]["enabled channels"] = list(
                filter((channelId).__ne__, portals[portal]["enabled channels"])
            )

    for edit in numberEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customNumber = edit["custom number"]
        if customNumber:
            portals[portal].setdefault("custom channel numbers", {})
            portals[portal]["custom channel numbers"].update({channelId: customNumber})
        else:
            portals[portal]["custom channel numbers"].pop(channelId)

    for edit in nameEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customName = edit["custom name"]
        if customName:
            portals[portal].setdefault("custom channel names", {})
            portals[portal]["custom channel names"].update({channelId: customName})
        else:
            portals[portal]["custom channel names"].pop(channelId)

    for edit in genreEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customGenre = edit["custom genre"]
        if customGenre:
            portals[portal].setdefault("custom genres", {})
            portals[portal]["custom genres"].update({channelId: customGenre})
        else:
            portals[portal]["custom genres"].pop(channelId)

    for edit in epgEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customEpgId = edit["custom epg id"]
        if customEpgId:
            portals[portal].setdefault("custom epg ids", {})
            portals[portal]["custom epg ids"].update({channelId: customEpgId})
        else:
            portals[portal]["custom epg ids"].pop(channelId)

    for edit in fallbackEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        channelName = edit["channel name"]
        if channelName:
            portals[portal].setdefault("fallback channels", {})
            portals[portal]["fallback channels"].update({channelId: channelName})
        else:
            portals[portal]["fallback channels"].pop(channelId)

    savePortals(portals)
    logger.info("Playlist config saved!")
    flash("Playlist config saved!", "success")
    return redirect("/editor", code=302)


@app.route("/editor/reset", methods=["POST"])
@authorise
def editorReset():
    portals = getPortals()
    for portal in portals:
        portals[portal]["enabled channels"] = []
        portals[portal]["custom channel numbers"] = {}
        portals[portal]["custom channel names"] = {}
        portals[portal]["custom genres"] = {}
        portals[portal]["custom epg ids"] = {}
        portals[portal]["fallback channels"] = {}

    savePortals(portals)
    logger.info("Playlist reset!")
    flash("Playlist reset!", "success")
    return redirect("/editor", code=302)


@app.route("/settings", methods=["GET"])
@authorise
def settings():
    settings = getSettings()
    return render_template(
        "settings.html", settings=settings, defaultSettings=defaultSettings
    )


@app.route("/settings/save", methods=["POST"])
@authorise
def save():
    settings = {}

    for setting, _ in defaultSettings.items():
        value = request.form.get(setting, "false")
        settings[setting] = value

    saveSettings(settings)
    logger.info("Settings saved!")
    Thread(target=refresh_xmltv).start()
    flash("Settings saved!", "success")
    return redirect("/settings", code=302)

@app.route("/reloadplaylist", methods=["GET"])
@authorise
def reloadplaylist():
    global cached_playlist, last_playlist_host
    cached_playlist = None
    last_playlist_host = None  # The playlist will be updated next time it is downloaded
    flash("Kicking off playlist reload...", "success")

    user_dir = os.path.expanduser("~")
    cache_dir = os.path.join(user_dir, "Evilvir.us")
    os.makedirs(cache_dir, exist_ok=True)
    epgcache_file = os.path.join(cache_dir, "MacReplayEPG.xml")

    try:
        os.remove(epgcache_file)
    except:
        logger.warning("EPG Cache file ({}) already expired/deleted".format(epgcache_file))
        pass

    logger.warning("EPG Cache file ({}) deleted".format(epgcache_file))

    threading.Thread(target=refresh_xmltv, daemon=True).start()  # Force update in a separate thread
    Thread(target=refresh_lineup).start()  # Update the channel lineup for plex.

    return redirect("/portals", code=302)


# Route to serve the cached playlist.m3u
@app.route("/playlist.m3u", methods=["GET"])
@authorise
def playlist():
    global cached_playlist, last_playlist_host
    
    logger.info("Playlist Requested")
    
    # Detect the current host dynamically
    current_host = request.host or "127.0.0.1"
    
    # Regenerate the playlist if it is empty or the host has changed
    if cached_playlist is None or len(cached_playlist) == 0 or last_playlist_host != current_host:
        logger.info(f"Regenerating playlist due to host change: {last_playlist_host} -> {current_host}")
        last_playlist_host = current_host
        generate_playlist()

    return Response(cached_playlist, mimetype="text/plain")

# Function to manually trigger playlist update
@app.route("/update_playlistm3u", methods=["POST"])
def update_playlistm3u():
    generate_playlist()
    return Response("Playlist updated successfully", status=200)

def generate_playlist():
    global cached_playlist
    logger.info("Generating playlist.m3u...")

    # Detect the host dynamically from the request
    playlist_host = request.host or "127.0.0.1"
    
    channels = []
    portals = getPortals()

    for portal in portals:
        if portals[portal]["enabled"] == "true":
            enabledChannels = portals[portal].get("enabled channels", [])
            if len(enabledChannels) != 0:
                name = portals[portal]["name"]
                url = portals[portal]["url"]
                macs = list(portals[portal]["macs"].keys())
                prioritymacs = list(portals[portal]["prioritymacs"].keys())
                proxy = portals[portal]["proxy"]
                useragent = portals[portal]["useragent"]
                customChannelNames = portals[portal].get("custom channel names", {})
                customGenres = portals[portal].get("custom genres", {})
                customChannelNumbers = portals[portal].get("custom channel numbers", {})
                customEpgIds = portals[portal].get("custom epg ids", {})

                macsforprocessing = macs

                if prioritymacs is not None and len(prioritymacs) > 0:
                    macsforprocessing = prioritymacs
                    logger.info("Generating playlist using PRIORITY MAC's for Portal({})".format(name))

                for mac in macsforprocessing:
                    try:
                        token = stb.getToken(url, mac, proxy, useragent)
                        stb.getProfile(url, mac, token, proxy, useragent)
                        allChannels = stb.getAllChannels(url, mac, token, proxy, useragent)
                        genres = stb.getGenreNames(url, mac, token, proxy, useragent)

                        if allChannels and genres:
                            break #we got data, no need to check next mac
                    except:
                        if prioritymacs is not None and len(prioritymacs) > 0:
                            logger.info("Error Generating playlist using PRIORITY MAC's for Portal({}), check that Priority MAC's are still valid".format(name))
                        else:
                            logger.info(
                                "Error Generating playlist for Portal({}), check that Priority MAC's are still valid".format(name))
                        allChannels = None
                        genres = None

                if allChannels and genres:
                    for channel in allChannels:
                        channelId = str(channel.get("id"))
                        logo = str(channel.get("logo"))
                        xmltvid = str(channel["xmltv_id"])

                        if xmltvid is None or xmltvid == "":
                            xmltvid = channelId

                        if channelId in enabledChannels:
                            channelName = customChannelNames.get(channelId)
                            if channelName is None:
                                channelName = str(channel.get("name"))
                            genre = customGenres.get(channelId)
                            if genre is None:
                                genreId = str(channel.get("tv_genre_id"))
                                genre = str(genres.get(genreId))
                            channelNumber = customChannelNumbers.get(channelId)
                            if channelNumber is None:
                                channelNumber = str(channel.get("number"))
                            epgId = customEpgIds.get(channelId)
                            if epgId is None:
                                #epgId = channelName
                                epgId = "{}_{}".format(xmltvid, channelNumber)
                            channels.append(
                                "#EXTINF:-1"
                                + ' tvg-id="'
                                + epgId
                                + (
                                    '" tvg-chno="' + channelNumber
                                    if getSettings().get("use channel numbers", "true")
                                    == "true"
                                    else ""
                                )
                                + '" tvg-logo="' + logo
                                + (
                                    '" group-title="' + genre
                                    if getSettings().get("use channel genres", "true")
                                    == "true"
                                    else ""
                                )
                                + '",'
                                + channelName
                                + "\n"
                                + "http://"
                                + playlist_host  # Use the dynamically detected playlist host
                                + "/play/"
                                + portal
                                + "/"
                                + channelId
                            )
                else:
                    logger.error("Error making playlist for {}, skipping".format(name))

    # Sorting the playlist based on settings
    if getSettings().get("sort playlist by channel name", "true") == "true":
        channels.sort(key=lambda k: k.split(",")[1].split("\n")[0])
    if getSettings().get("use channel numbers", "true") == "true":
        if getSettings().get("sort playlist by channel number", "false") == "true":
            channels.sort(key=lambda k: k.split('tvg-chno="')[1].split('"')[0])
    if getSettings().get("use channel genres", "true") == "true":
        if getSettings().get("sort playlist by channel genre", "false") == "true":
            channels.sort(key=lambda k: k.split('group-title="')[1].split('"')[0])

    playlist = "#EXTM3U \n"
    playlist = playlist + "\n".join(channels)

    # Update the cache
    cached_playlist = playlist
    logger.info("Playlist generated and cached.")

def datetime_to_float(d):
    epoch = datetime.fromtimestamp(0, timezone.utc)
    total_seconds =  (d - epoch).total_seconds()
    # total_seconds will be in decimals (millisecond precision)
    return total_seconds

def float_to_datetime(fl):
    return datetime.fromtimestamp(fl, timezone.utc)

def refresh_xmltv():
    settings = getSettings()
    logger.info("Refreshing XMLTV...")

    # Set up paths for XMLTV cache
    user_dir = os.path.expanduser("~")
    cache_dir = os.path.join(user_dir, "Evilvir.us")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "MacReplayEPG.xml")

    portalcachepath = os.path.join(basePath, "evilvir.us", "portalcache")
    os.makedirs(portalcachepath, exist_ok=True)

    # Define date cutoff for programme filtering
    day_before_yesterday = datetime.now(timezone.utc) - timedelta(days=2)
    day_before_yesterday_str = day_before_yesterday.strftime("%Y%m%d%H%M%S") + " +0000"

    # Load existing cache if it exists
    cached_programmes = []
    if os.path.exists(cache_file):
        try:
            tree = ET.parse(cache_file)
            root = tree.getroot()
            for programme in root.findall("programme"):
                stop_attr = programme.get("stop")  # Get the 'stop' attribute
                if stop_attr:
                    try:
                        # Parse the stop time and compare with the cutoff
                        stop_time = datetime.strptime(stop_attr.split(" ")[0], "%Y%m%d%H%M%S")
                        #if stop_time.timestamp() >= day_before_yesterday.timestamp(): #after fixing day_before_yesterday to be aware, this threw this error "can't compare offset-naive and offset-aware datetimes"
                        if stop_time.timestamp() >= day_before_yesterday.timestamp():  # Keep only recent programmes
                            cached_programmes.append(ET.tostring(programme, encoding="unicode"))
                    except ValueError as e:
                        logger.warning(f"Invalid stop time format in cached programme: {stop_attr}. Skipping.")
            logger.info("Loaded existing programme data from cache.")
        except Exception as e:
            logger.error(f"Failed to load cache file: {e}")

    # Initialize new XMLTV data
    channels = ET.Element("tv")
    programmes = ET.Element("tv")
    portals = getPortals()

    for portal in portals:
        if portals[portal]["enabled"] == "true":
            portal_name = portals[portal]["name"]
            portal_epg_offset = int(portals[portal]["epg offset"])
            logger.info(f"Fetching EPG | Portal: {portal_name} | offset: {portal_epg_offset} |")

            enabledChannels = portals[portal].get("enabled channels", [])
            if len(enabledChannels) != 0:
                name = portals[portal]["name"]
                url = portals[portal]["url"]
                macs = list(portals[portal]["macs"].keys())
                prioritymacs = list(portals[portal]["prioritymacs"].keys())
                proxy = portals[portal]["proxy"]
                customChannelNames = portals[portal].get("custom channel names", {})
                customEpgIds = portals[portal].get("custom epg ids", {})
                customChannelNumbers = portals[portal].get("custom channel numbers", {})
                useragent = portals[portal]["useragent"]

                macsforprocessing = macs

                if prioritymacs is not None and len(prioritymacs) > 0:
                    macsforprocessing = prioritymacs
                    logger.info("Generating EPG using PRIORITY MAC's for Portal({})".format(name))

                for mac in macsforprocessing:
                    try:
                        token = stb.getToken(url, mac, proxy, useragent)
                        profile = stb.getProfile(url, mac, token, proxy, useragent)
                        allChannels = stb.getAllChannels(url, mac, token, proxy, useragent)
                        epg = stb.getEpg(url, mac, token, 48, proxy, useragent)
                        #lcl = stb.getlocalization(url, proxy, useragent)

                        timenowutc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
                        timenowutcstr = timenowutc.strftime("%Y%m%d%H%M%S") + " +0000"
                        timenowutcwithoffset = timenowutc + timedelta(hours=portal_epg_offset)
                        timenowutcwithoffsetstr = timenowutcwithoffset.strftime("%Y%m%d%H%M%S") + " +0000"

                        logger.info("Portal({}), MAC({}): Profile data - \"default_timezone\": {}, \"timezone_diff\" {}".format(name, mac, profile["default_timezone"], profile["timezone_diff"]))
                        logger.info("Time Now (UTC) \"{}\", Portal EPG Offset: {}, Time Now with Offset \"{}\"".format(timenowutcstr, portal_epg_offset, timenowutcwithoffsetstr))

                        if epg is not None:
                            #write raw epg file to disk for debugging
                            portalprofiledatafilename = name.replace(" ", "_")
                            portalprofiledatafilename = portalprofiledatafilename.replace("'", "")
                            portalprofiledatafilename = portalprofiledatafilename.replace("\"", "")
                            portalprofiledatafilename = portalprofiledatafilename.replace(",", "_")
                            raw_epg_file = os.path.join(portalcachepath, "{}_RawEPG.json".format(portalprofiledatafilename))
                            with open(raw_epg_file, "w", encoding="utf-8") as f:
                                json.dump(epg, f, indent=4)
                            break # we got data, no need ot look at next mac
                    except Exception as e:
                        allChannels = None
                        epg = None
                        if prioritymacs is not None and len(prioritymacs) > 0:
                            logger.info("Error Fetching EPG data using PRIORITY MAC's for Portal({}), check that Priority MAC's are still valid".format(name))
                        else:
                            logger.info("Error Fetching EPG data for Portal({}), check that MAC's are still valid, MAC {}: {}".format(name, mac, e))
                            #logger.error(f"Error fetching data for MAC {mac}: {e}")

                if allChannels and epg:
                    for channel in allChannels:
                        # initialize
                        channelName = ""
                        channelNumber = ""

                        try:
                            channelId = str(channel.get("id"))
                            xmltvid = str(channel.get("xmltv_id"))
                            if xmltvid is None or xmltvid == "":
                                xmltvid = channelId


                            if str(channelId) in enabledChannels:
                                channelName = customChannelNames.get(channelId, channel.get("name"))
                                channelNumber = customChannelNumbers.get(channelId, str(channel.get("number")))
                                epgId = customEpgIds.get(channelId, channelNumber)

                                if len(customEpgIds) == 0:
                                    epgId = "{}_{}".format(xmltvid, channelNumber)

                                channelEle = ET.SubElement(
                                    channels, "channel", id=epgId
                                )
                                ET.SubElement(channelEle, "display-name").text = channelName
                                ET.SubElement(channelEle, "icon", src=channel.get("logo"))

                                if channelId not in epg or not epg.get(channelId):
                                    logger.warning(f"No EPG data found for channel {channelName.encode("utf-8")} (ID: {channelId.encode("utf-8")}), Creating a Dummy EPG item.")
                                    start_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
                                    stop_time = start_time + timedelta(hours=24)
                                    start = start_time.strftime("%Y%m%d%H%M%S") + " +0000"
                                    stop = stop_time.strftime("%Y%m%d%H%M%S") + " +0000"
                                    programmeEle = ET.SubElement(
                                        programmes,
                                        "programme",
                                        start=start,
                                        stop=stop,
                                        channel=epgId,
                                    )
                                    ET.SubElement(programmeEle, "title").text = channelName
                                    ET.SubElement(programmeEle, "desc").text = channelName
                                else:
                                    for p in epg.get(channelId):
                                        try:
                                            #start_timeold = datetime.utcfromtimestamp(p.get("start_timestamp")) + timedelta(hours=portal_epg_offset)
                                            #stop_timeold = datetime.utcfromtimestamp(p.get("stop_timestamp")) + timedelta(hours=portal_epg_offset)
                                            #start_time = datetime.fromtimestamp(p.get("start_timestamp"), timezone.utc)
                                            #stop_time = datetime.fromtimestamp(p.get("stop_timestamp"), timezone.utc)
                                            start_time = datetime.fromtimestamp(p.get("start_timestamp"),timezone.utc) + timedelta(hours=portal_epg_offset)
                                            stop_time = datetime.fromtimestamp(p.get("stop_timestamp"),timezone.utc) + timedelta(hours=portal_epg_offset)
                                            #startold = start_timeold.strftime("%Y%m%d%H%M%S") + " +0000"
                                            #stopold = stop_timeold.strftime("%Y%m%d%H%M%S") + " +0000"
                                            start = start_time.strftime("%Y%m%d%H%M%S")
                                            stop = stop_time.strftime("%Y%m%d%H%M%S")
                                            #start = start_time.strftime("%Y%m%d%H%M%S") + " +0000"
                                            #stop = stop_time.strftime("%Y%m%d%H%M%S") + " +0000"
                                            #if start <= day_before_yesterday_str:
                                            #    continue

                                            programmeEle = ET.SubElement(
                                                programmes,
                                                "programme",
                                                start=start,
                                                stop=stop,
                                                channel=epgId,
                                            )
                                            ET.SubElement(programmeEle, "title").text = p.get("name")
                                            ET.SubElement(programmeEle, "desc").text = p.get("descr")
                                        except Exception as e:
                                            logger.error(f"Error processing programme for channel {channelName} (ID: {channelId}): {e}")
                                            pass
                        except Exception as e:
                            if channelNumber and channelName:
                                logger.error(f"| Channel:{channelNumber} | {channelName} | {e}")
                            else:
                                logger.error(f"| Error iterating epg data: {e}")
                            pass
                else:
                    logger.error(f"Error making XMLTV for {name}, skipping")

    # Combine channels and programmes into a single XML document
    xmltv = channels
    for programme in programmes.iter("programme"):
        xmltv.append(programme)

    # Add cached programmes, ensuring no duplicates
    existing_programme_hashes = {ET.tostring(p, encoding="unicode") for p in xmltv.findall("programme")}
    for cached in cached_programmes:
        if cached not in existing_programme_hashes:
            xmltv.append(ET.fromstring(cached))

    # Pretty-print the XML with blank line removal
    rough_string = ET.tostring(xmltv, encoding="unicode")
    reparsed = minidom.parseString(rough_string)
    formatted_xmltv = "\n".join([line for line in reparsed.toprettyxml(indent="  ").splitlines() if line.strip()])

    # Save updated cache
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(formatted_xmltv)
    logger.info("XMLTV cache updated.")

    # Update global cache
    global cached_xmltv, last_updated
    cached_xmltv = formatted_xmltv
    last_updated = time.time()
    logger.debug(f"Generated XMLTV: {formatted_xmltv}")
    
# Endpoint to get the XMLTV data
@app.route("/xmltv", methods=["GET"])
@authorise
def xmltv():
    global cached_xmltv, last_updated
    logger.info("Guide Requested")
    
    # Check if the cached XMLTV data is older than 15 minutes
    if cached_xmltv is None or (time.time() - last_updated) > 900:  # 900 seconds = 15 minutes
        refresh_xmltv()
    
    return Response(
        cached_xmltv,
        mimetype="text/xml",
    )


@app.route("/play/<portalId>/<channelId>", methods=["GET"])
def channel(portalId, channelId):
    def streamData():
        def occupy():
            occupied.setdefault(portalId, [])
            occupied.get(portalId, []).append(
                {
                    "portalId": portalId,
                    "mac": mac,
                    "channel id": channelId,
                    "channel name": channelName,
                    "client": ip,
                    "portal name": portalName,
                    "start time": startTime,
                }
            )
            logger.info("Occupied Portal({}):MAC({})".format(portalId, mac))

        def unoccupy():
            occupied.get(portalId, []).remove(
                {
                    "portalId": portalId,
                    "mac": mac,
                    "channel id": channelId,
                    "channel name": channelName,
                    "client": ip,
                    "portal name": portalName,
                    "start time": startTime,
                }
            )
            logger.info("Unoccupied Portal({}):MAC({})".format(portalId, mac))

        try:
            startTime = datetime.now(timezone.utc).timestamp()
            occupy()
            with subprocess.Popen(
                ffmpegcmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            ) as ffmpeg_sp:
                while True:
                    chunk = ffmpeg_sp.stdout.read(1024)
                    if len(chunk) == 0:
                        if ffmpeg_sp.poll() != 0:
                            logger.info("Ffmpeg closed with error({}). Moving MAC({}) for Portal({})".format(str(ffmpeg_sp.poll()), mac, portalName))
                            moveMac(portalId, mac)
                        break
                    yield chunk
        except:
            pass
        finally:
            unoccupy()
            ffmpeg_sp.kill()

    def testStream():
        timeout = int(getSettings()["ffmpeg timeout"]) * int(1000000)
        ffprobecmd = [ffprobe_path, "-timeout", str(timeout), "-i", link]

        if proxy:
            ffprobecmd.insert(1, "-http_proxy")
            ffprobecmd.insert(2, proxy)

        with subprocess.Popen(
            ffprobecmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as ffprobe_sb:
            ffprobe_sb.communicate()
            if ffprobe_sb.returncode == 0:
                return True
            else:
                return False

    def isMacFree():
        count = 0
        for i in occupied.get(portalId, []):
            if i["mac"] == mac:
                count = count + 1
        if count < streamsPerMac:
            return True
        else:
            return False

    portal = getPortals().get(portalId)
    portalName = portal.get("name")
    url = portal.get("url")
    macs = list(portal["macs"].keys())
    streamsPerMac = int(portal.get("streams per mac"))
    proxy = portal.get("proxy")
    web = request.args.get("web")
    ip = request.remote_addr
    useragent = portal.get("useragent")

    logger.info(
        "IP({}) requested Portal({}):Channel({})".format(ip, portalId, channelId)
    )

    freeMac = False

    for mac in macs:
        channels = None
        cmd = None
        link = None
        if streamsPerMac == 0 or isMacFree():
            logger.info(
                "Trying Portal({}):MAC({}):Channel({})".format(portalId, mac, channelId)
            )
            freeMac = True
            token = stb.getToken(url, mac, proxy, useragent)
            if token:
                stb.getProfile(url, mac, token, proxy, useragent)
                channels = stb.getAllChannels(url, mac, token, proxy, useragent)

        if channels:
            for c in channels:
                if str(c["id"]) == channelId:
                    channelName = portal.get("custom channel names", {}).get(channelId)
                    if channelName == None:
                        channelName = c["name"]
                    cmd = c["cmd"]
                    break

        if cmd:
            if "http://localhost/" in cmd:
                link = stb.getLink(url, mac, token, cmd, proxy, useragent)
            else:
                link = cmd.split(" ")[1]

        if link:

            logger.info(
                "Source stream found for Portal({}):Channel({}):Url({})".format(
                    portalId, channelId, link
                )
            )

            if getSettings().get("test streams", "true") == "false" or testStream():
                if web:
                    ffmpegcmd = [
                        ffmpeg_path,
                        "-loglevel",
                        "panic",
                        "-hide_banner",
                        "-i",
                        link,
                        "-vcodec",
                        "copy",
                        "-f",
                        "mp4",
                        "-movflags",
                        "frag_keyframe+empty_moov",
                        "pipe:",
                    ]
                    if proxy:
                        ffmpegcmd.insert(1, "-http_proxy")
                        ffmpegcmd.insert(2, proxy)

                        logger.info(
                            "FFMPEG cmd w/proxy issued({})".format(
                                ffmpegcmd
                            )
                        )

                    return Response(streamData(), mimetype="application/octet-stream")

                else:
                    if getSettings().get("stream method", "ffmpeg") == "ffmpeg":
                        ffmpegcmd = f"{ffmpeg_path} {getSettings()['ffmpeg command']}"
                        ffmpegcmd = ffmpegcmd.replace("<url>", link)
                        ffmpegcmd = ffmpegcmd.replace(
                            "<timeout>",
                            str(int(getSettings()["ffmpeg timeout"]) * int(1000000)),
                        )


                        if proxy:
                            ffmpegcmd = ffmpegcmd.replace("<proxy>", proxy)
                        else:
                            ffmpegcmd = ffmpegcmd.replace("-http_proxy <proxy>", "")
                        " ".join(ffmpegcmd.split())  # cleans up multiple whitespaces

                        if useragent:
                            useragent = useragent.replace(" ", "%20")
                            ffmpegcmd = ffmpegcmd.replace("<headers>", "-headers 'User-Agent:%20{}'".format(useragent))
                        else:
                            ffmpegcmd = ffmpegcmd.replace("<headers>", "")


                        ffmpegcmd = ffmpegcmd.split()

                        #restore spaces marked as %20 by creating a temp list for modifications
                        ffmpegcmdtemp = []
                        for cmd in ffmpegcmd:
                            cmd = cmd.replace("%20", " ")
                            ffmpegcmdtemp.append(cmd)

                        #copy temp list back to ffmpegcmd
                        if ffmpegcmdtemp:
                            ffmpegcmd = ffmpegcmdtemp

                        logger.info(
                            "FFMPEG cmd issued({})".format(
                                ffmpegcmd
                            )
                        )

                        return Response(
                            streamData(), mimetype="application/octet-stream"
                        )
                    else:
                        logger.info("Redirect sent")
                        return redirect(link)

        logger.info(
            "Unable to connect to Portal({}) using MAC({})".format(portalId, mac)
        )
        logger.info("Moving MAC({}) for Portal({})".format(mac, portalName))
        moveMac(portalId, mac)

        if not getSettings().get("try all macs", "true") == "true":
            break

    if not web:
        logger.info(
            "Portal({}):Channel({}) is not working. Looking for fallbacks...".format(
                portalId, channelId
            )
        )

        portals = getPortals()
        for portal in portals:
            if portals[portal]["enabled"] == "true":
                fallbackChannels = portals[portal]["fallback channels"]
                if channelName in fallbackChannels.values():
                    url = portals[portal].get("url")
                    macs = list(portals[portal]["macs"].keys())
                    proxy = portals[portal].get("proxy")
                    useragent = portals[portal].get("useragent")
                    for mac in macs:
                        channels = None
                        cmd = None
                        link = None
                        if streamsPerMac == 0 or isMacFree():
                            for k, v in fallbackChannels.items():
                                if v == channelName:
                                    try:
                                        token = stb.getToken(url, mac, proxy, useragent)
                                        stb.getProfile(url, mac, token, proxy, useragent)
                                        channels = stb.getAllChannels(
                                            url, mac, token, proxy, useragent
                                        )
                                    except:
                                        logger.info(
                                            "Unable to connect to fallback Portal({}) using MAC({})".format(
                                                portalId, mac
                                            )
                                        )
                                    if channels:
                                        fChannelId = k
                                        for c in channels:
                                            if str(c["id"]) == fChannelId:
                                                cmd = c["cmd"]
                                                break
                                        if cmd:
                                            if "http://localhost/" in cmd:
                                                link = stb.getLink(
                                                    url, mac, token, cmd, proxy, useragent
                                                )
                                            else:
                                                link = cmd.split(" ")[1]
                                            if link:
                                                logger.info(
                                                    "Source stream found for Portal({}):Channel({}):Url({})".format(
                                                        portalId, channelId, link
                                                    )
                                                )
                                                if testStream():
                                                    logger.info(
                                                        "Fallback found for Portal({}):Channel({})".format(
                                                            portalId, channelId
                                                        )
                                                    )
                                                    if (
                                                        getSettings().get(
                                                            "stream method", "ffmpeg"
                                                        )
                                                        == "ffmpeg"
                                                    ):
                                                        ffmpegcmd = ffmpeg_path + " " + str(
                                                            getSettings()[
                                                                "ffmpeg command"
                                                            ]
                                                        )
                                                        ffmpegcmd = ffmpegcmd.replace(
                                                            "<url>", link
                                                        )
                                                        ffmpegcmd = ffmpegcmd.replace(
                                                            "<timeout>",
                                                            str(
                                                                int(
                                                                    getSettings()[
                                                                        "ffmpeg timeout"
                                                                    ]
                                                                )
                                                                * int(1000000)
                                                            ),
                                                        )


                                                        if proxy:
                                                            ffmpegcmd = (
                                                                ffmpegcmd.replace(
                                                                    "<proxy>", proxy
                                                                )
                                                            )
                                                        else:
                                                            ffmpegcmd = ffmpegcmd.replace(
                                                                "-http_proxy <proxy>",
                                                                "",
                                                            )
                                                        " ".join(
                                                            ffmpegcmd.split()
                                                        )  # cleans up multiple whitespaces

                                                        #can't split headers to use a useragent so add after
                                                        if useragent:
                                                            ffmpegcmd = (
                                                                ffmpegcmd.replace(
                                                                    "<headers>", "-headers 'User-Agent:%20{}'".format(useragent)
                                                                )
                                                            )
                                                        else:
                                                            ffmpegcmd = ffmpegcmd.replace(
                                                                "<headers>",
                                                                "",
                                                            )

                                                        ffmpegcmd = ffmpegcmd.split()

                                                        # restore spaces marked as %20 by creating a temp list for modifications
                                                        ffmpegcmdtemp = []
                                                        for cmd in ffmpegcmd:
                                                            cmd = cmd.replace("%20", " ")
                                                            ffmpegcmdtemp.append(cmd)

                                                        # copy temp list back to ffmpegcmd
                                                        if ffmpegcmdtemp:
                                                            ffmpegcmd = ffmpegcmdtemp

                                                        logger.info(
                                                            "FFMPEG cmd issued({})".format(
                                                                ffmpegcmd
                                                            )
                                                        )

                                                        return Response(
                                                            streamData(),
                                                            mimetype="application/octet-stream",
                                                        )
                                                    else:
                                                        logger.info("Redirect sent")
                                                        return redirect(link)

    if freeMac:
        logger.info(
            "No working streams found for Portal({}):Channel({})".format(
                portalId, channelId
            )
        )
    else:
        logger.info(
            "No free MAC for Portal({}):Channel({})".format(portalId, channelId)
        )

    return make_response("No streams available", 503)


@app.route("/dashboard")
@authorise
def dashboard():
    return render_template("dashboard.html")


@app.route("/streaming")
@authorise
def streaming():
    return flask.jsonify(occupied)


@app.route("/log")
@authorise
def log():
    # Get the base path for the user directory
    basePath = os.path.expanduser("~")

    # Define the path for the log file in the 'evilvir.us' subdirectory
    logFilePath = os.path.join(basePath, "evilvir.us", "MacReplay.log")

    # Ensure the subdirectory exists
    os.makedirs(os.path.dirname(logFilePath), exist_ok=True)

    # Open and read the log file
    with open(logFilePath) as f:
        log_content = f.read()
    
    return log_content


@app.route("/keepalive")
@authorise
def keepalive():
    return keepalive_watchdog()


# HD Homerun #


def hdhr(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        settings = getSettings()
        security = settings["enable security"]
        username = settings["username"]
        password = settings["password"]
        hdhrenabled = settings["enable hdhr"]
        if (
            security == "false"
            or auth
            and auth.username == username
            and auth.password == password
        ):
            if hdhrenabled:
                return f(*args, **kwargs)
        return make_response("Error", 404)

    return decorated


@app.route("/discover.json", methods=["GET"])
@hdhr
def discover():
    logger.info("HDHR Status Requested.")
    settings = getSettings()
    name = settings["hdhr name"]
    id = settings["hdhr id"]
    tuners = settings["hdhr tuners"]
    data = {
        "BaseURL": host,
        "DeviceAuth": name,
        "DeviceID": id,
        "FirmwareName": "MacReplay",
        "FirmwareVersion": "666",
        "FriendlyName": name,
        "LineupURL": host + "/lineup.json",
        "Manufacturer": "Evilvirus",
        "ModelNumber": "666",
        "TunerCount": int(tuners),
    }
    return flask.jsonify(data)


@app.route("/lineup_status.json", methods=["GET"])
@hdhr
def status():
    data = {
        "ScanInProgress": 0,
        "ScanPossible": 0,
        "Source": "Cable",
        "SourceList": ["Cable"],
    }
    return flask.jsonify(data)


# Function to refresh the lineup
def refresh_lineup():
    global cached_lineup
    logger.info("Refreshing Lineup...")
    lineup = []
    portals = getPortals()
    for portal in portals:
        if portals[portal]["enabled"] == "true":
            enabledChannels = portals[portal].get("enabled channels", [])
            if len(enabledChannels) != 0:
                name = portals[portal]["name"]
                url = portals[portal]["url"]
                macs = list(portals[portal]["macs"].keys())
                prioritymacs = list(portals[portal]["prioritymacs"].keys())
                proxy = portals[portal]["proxy"]
                useragent = portals[portal]["useragent"]
                customChannelNames = portals[portal].get("custom channel names", {})
                customChannelNumbers = portals[portal].get("custom channel numbers", {})

                macsforprocessing = macs

                if prioritymacs is not None and len(prioritymacs) > 0:
                    macsforprocessing = prioritymacs
                    logger.info("Refreshing lineup Using PRIORITY MAC's for Portal({})".format(name))

                for mac in macsforprocessing:
                    try:
                        token = stb.getToken(url, mac, proxy, useragent)
                        stb.getProfile(url, mac, token, proxy, useragent)
                        allChannels = stb.getAllChannels(url, mac, token, proxy, useragent)

                        if allChannels:
                            break #we got data, no need to check next mac
                    except:
                        allChannels = None

                if allChannels:
                    for channel in allChannels:
                        channelId = str(channel.get("id"))
                        if channelId in enabledChannels:
                            channelName = customChannelNames.get(channelId)
                            if channelName is None:
                                channelName = str(channel.get("name"))
                            channelNumber = customChannelNumbers.get(channelId)
                            if channelNumber is None:
                                channelNumber = str(channel.get("number"))

                            lineup.append(
                                {
                                    "GuideNumber": channelNumber,
                                    "GuideName": channelName,
                                    "URL": "http://"
                                    + host
                                    + "/play/"
                                    + portal
                                    + "/"
                                    + channelId,
                                }
                            )
                else:
                    logger.error("Error making lineup for {}, skipping".format(name))
    
    # Sort lineup by GuideNumber
    lineup.sort(key=lambda x: int(x["GuideNumber"]))

    cached_lineup = lineup
    logger.info("Lineup Refreshed.")
    
    
# Endpoint to get the current lineup
@app.route("/lineup.json", methods=["GET"])
@app.route("/lineup.post", methods=["POST"])
@hdhr
def lineup():
    logger.info("Lineup Requested")
    if not cached_lineup:  # Refresh lineup if cache is empty
        refresh_lineup()
    logger.info("Lineup Delivered")
    return jsonify(cached_lineup)

# Endpoint to manually refresh the lineup
@app.route("/refresh_lineup", methods=["POST"])
def refresh_lineup_endpoint():
    refresh_lineup()
    return jsonify({"status": "Lineup refreshed successfully"})

def start_refresh():
    # Run refresh_lineup in a separate thread
    threading.Thread(target=refresh_lineup, daemon=True).start()
    threading.Thread(target=refresh_xmltv, daemon=True).start()


    
if __name__ == "__main__":
    config = loadConfig()

    # Start the refresh thread before the server
    #unnecessary, the first request to /xmltv or /playlist would call the methods contained within. Actually found doubling up on calls happening at times when reloading server
    # start_refresh()

    def keepalivethread():
        while True:
            kainterval = getSettings().get("ka interval")

            if kainterval is not None and int(kainterval) >= 1:
                keepalive_watchdog()
                time.sleep(int(kainterval)*60)
            else:
                logger.info("Portal Keep-Alive Interval invalid, must be at least 1 minute")
                time.sleep(60)


    kat = threading.Thread(name='keep-alive thread', target=keepalivethread)
    kat.daemon = True
    kat.start()

    # Start the server
    if "TERM_PROGRAM" in os.environ.keys() and os.environ["TERM_PROGRAM"] == "vscode":
        app.run(host="0.0.0.0", port=8001, debug=True)
    else:
        waitress.serve(app, port=8001, _quiet=True, threads=24)

