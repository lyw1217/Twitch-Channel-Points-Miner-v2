import json
import re
import time
from base64 import b64encode
import requests
from twitch_data import *
from twitch_data import get_streamer_url, USER_AGENT


# Twitch client sends some statistics as base64-encoded json
# This API is presumably called Spade (https://github.com/twitchscience/spade)
# "minute-watched" requests are what Twitch uses to know if you're watching a stream, and to grant you channel points.


class RequestInfo:
    def __init__(self, url, payload):
        self.url = url
        self.payload = payload


# "minute-watched" request for each streamer
minute_watched_requests = {}


def send_minute_watched_events():
    headers = {"user-agent": USER_AGENT}
    streamers = get_streamer_logins()
    minutes_passed = 0
    while True:
        for streamer_login in streamers:
            next_iteration = time.time() + 60 / len(streamers)
            if is_online(streamer_login):
                # print(f"Watching minute for {streamer_login}")
                request_info = minute_watched_requests[streamer_login]
                requests.post(request_info.url, data=request_info.payload, headers=headers)
            elif minutes_passed % 5 == 0:
                # checking whether the streamer is online every 5 minutes
                check_online(streamer_login)

            time.sleep(max(next_iteration - time.time(), 0))

        minutes_passed += 1


def update_minute_watched_event_request(streamer_login):
    event_properties = {
        "channel_id": get_channel_id(streamer_login),
        "broadcast_id": get_broadcast_id(streamer_login),
        "player": "site",
        "user_id": get_user_id(),
    }
    minute_watched = [{"event": "minute-watched", "properties": event_properties}]
    json_event = json.dumps(minute_watched, separators=(',', ':'))
    after_base64 = (b64encode(json_event.encode("utf-8"))).decode("utf-8")
    payload = {"data": after_base64}
    url = get_minute_watched_request_url(streamer_login)
    minute_watched_requests[streamer_login] = RequestInfo(url, payload)


def get_minute_watched_request_url(streamer_login):
    main_page_request = requests.get(get_streamer_url(streamer_login),
                                     headers={"User-Agent": USER_AGENT})
    response = main_page_request.text
    settings_url = re.search("(https://static.twitchcdn.net/config/settings.*?js)", response).group(1)

    settings_request = requests.get(settings_url, headers={"User-Agent": USER_AGENT})
    response = settings_request.text
    minute_watched_request_url = re.search('"spade_url":"(.*?)"', response).group(1)
    return minute_watched_request_url
