# -*- coding: utf-8 -*-

import copy
import logging
import random
import signal
import sys
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime

from TwitchChannelPointsMiner.classes.entities.PubsubTopic import PubsubTopic
from TwitchChannelPointsMiner.classes.entities.Streamer import (
    Streamer,
    StreamerSettings,
)
from TwitchChannelPointsMiner.classes.Exceptions import StreamerDoesNotExistException
from TwitchChannelPointsMiner.classes.Settings import Settings
from TwitchChannelPointsMiner.classes.Twitch import Twitch
from TwitchChannelPointsMiner.classes.WebSocketsPool import WebSocketsPool
from TwitchChannelPointsMiner.logger import LoggerSettings, configure_loggers
from TwitchChannelPointsMiner.utils import (
    _millify,
    at_least_one_value_in_settings_is,
    get_user_agent,
    internet_connection_available,
    set_default_settings,
)

# Suppress:
#   - chardet.charsetprober - [feed]
#   - chardet.charsetprober - [get_confidence]
#   - requests - [Starting new HTTPS connection (1)]
logging.getLogger("chardet.charsetprober").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


class TwitchChannelPointsMiner:
    __slots__ = [
        "username",
        "twitch",
        "claim_drops_startup",
        "streamers",
        "events_predictions",
        "minute_watcher_thread",
        "ws_pool",
        "session_id",
        "running",
        "start_datetime",
        "original_streamers",
        "logs_file",
    ]

    def __init__(
        self,
        username: str,
        claim_drops_startup: bool = False,
        # This settings will be global shared trought Settings class
        logger_settings: LoggerSettings = LoggerSettings(),
        # Default values for all streamers
        streamer_settings: StreamerSettings = StreamerSettings(),
    ):
        self.username = username

        # Set as global config
        Settings.logger = logger_settings

        # Init as default all the missing values
        streamer_settings.default()
        streamer_settings.bet.default()
        Settings.streamer_settings = streamer_settings

        user_agent = get_user_agent("FIREFOX")
        self.twitch = Twitch(self.username, user_agent)

        self.claim_drops_startup = claim_drops_startup
        self.streamers = []
        self.events_predictions = {}
        self.minute_watcher_thread = None
        self.ws_pool = None

        self.session_id = str(uuid.uuid4())
        self.running = False
        self.start_datetime = None
        self.original_streamers = []

        self.logs_file = configure_loggers(self.username, logger_settings)

        for sign in [signal.SIGINT, signal.SIGSEGV, signal.SIGTERM]:
            signal.signal(sign, self.end)

    def mine(self, streamers: list = [], followers=False):
        self.run(streamers, followers)

    def run(self, streamers: list = [], followers=False):
        if self.running:
            logger.error("You can't start multiple sessions of this instance!")
        else:
            logger.info(
                f"Start session: '{self.session_id}'", extra={"emoji": ":bomb:"}
            )
            self.running = True
            self.start_datetime = datetime.now()

            self.twitch.login()

            if self.claim_drops_startup is True:
                self.twitch.claim_all_drops_from_inventory()

            streamers_name: list = []
            streamers_dict: dict = {}

            for streamer in streamers:
                username = (
                    streamer.username
                    if isinstance(streamer, Streamer)
                    else streamer.lower().strip()
                )
                streamers_name.append(username)
                streamers_dict[username] = streamer

            if followers is True:
                followers_array = self.twitch.get_followers()
                logger.info(
                    f"Load {len(followers_array)} followers from your profile!",
                    extra={"emoji": ":clipboard:"},
                )
                for username in followers_array:
                    if username not in streamers_dict:
                        streamers_dict[username] = username.lower().strip()
            else:
                followers_array = []

            streamers_name = list(
                OrderedDict.fromkeys(streamers_name + followers_array)
            )

            logger.info(
                f"Loading data for {len(streamers_name)} streamers. Please wait...",
                extra={"emoji": ":nerd_face:"},
            )
            for username in streamers_name:
                time.sleep(random.uniform(0.3, 0.7))
                try:

                    if isinstance(streamers_dict[username], Streamer) is True:
                        streamer = streamers_dict[username]
                    else:
                        streamer = Streamer(username)

                    streamer.channel_id = self.twitch.get_channel_id(username)
                    streamer.settings = set_default_settings(
                        streamer.settings, Settings.streamer_settings
                    )
                    streamer.settings.bet = set_default_settings(
                        streamer.settings.bet, Settings.streamer_settings.bet
                    )

                    self.streamers.append(streamer)
                except StreamerDoesNotExistException:
                    logger.info(
                        f"Streamer {username} does not exist",
                        extra={"emoji": ":cry:"},
                    )

            # Populate the streamers with default values.
            # 1. Load channel points and auto-claim bonus
            # 2. Check if streamers are online
            # 3. Check if the user is a Streamer. In thi case you can't do prediction
            for streamer in self.streamers:
                time.sleep(random.uniform(0.3, 0.7))
                self.twitch.load_channel_points_context(streamer)
                self.twitch.check_streamer_online(streamer)
                self.twitch.viewer_is_mod(streamer)
                if streamer.viewer_is_mod is True:
                    streamer.settings.make_predictions = False

            self.original_streamers = copy.deepcopy(self.streamers)

            # If we have at least one streamer with settings = make_predictions True
            make_predictions = at_least_one_value_in_settings_is(
                self.streamers, "make_predictions", True
            )

            self.minute_watcher_thread = threading.Thread(
                target=self.twitch.send_minute_watched_events,
                args=(
                    self.streamers,
                    at_least_one_value_in_settings_is(
                        self.streamers, "watch_streak", True
                    ),
                ),
            )
            self.minute_watcher_thread.name = "Minute watcher"
            self.minute_watcher_thread.start()

            self.ws_pool = WebSocketsPool(
                twitch=self.twitch,
                streamers=self.streamers,
                events_predictions=self.events_predictions,
            )

            # Subscribe to community-points-user. Get update for points spent or gains
            self.ws_pool.submit(
                PubsubTopic(
                    "community-points-user-v1",
                    user_id=self.twitch.twitch_login.get_user_id(),
                )
            )

            # If we have at least one streamer with settings = claim_drops True
            # Going to subscribe to user-drop-events. Get update for drop-progress
            claim_drops = at_least_one_value_in_settings_is(
                self.streamers, "claim_drops", True
            )
            if claim_drops is True:
                self.ws_pool.submit(
                    PubsubTopic(
                        "user-drop-events",
                        user_id=self.twitch.twitch_login.get_user_id(),
                    )
                )

            # Going to subscribe to predictions-user-v1. Get update when we place a new prediction (confirm)
            if make_predictions is True:
                self.ws_pool.submit(
                    PubsubTopic(
                        "predictions-user-v1",
                        user_id=self.twitch.twitch_login.get_user_id(),
                    )
                )

            for streamer in self.streamers:
                self.ws_pool.submit(
                    PubsubTopic("video-playback-by-id", streamer=streamer)
                )

                if streamer.settings.follow_raid is True:
                    self.ws_pool.submit(PubsubTopic("raid", streamer=streamer))

                if streamer.settings.make_predictions is True:
                    self.ws_pool.submit(
                        PubsubTopic("predictions-channel-v1", streamer=streamer)
                    )

            while self.running:
                time.sleep(random.uniform(20, 60))
                # Do an external control for WebSocket. Check if the thread is running
                # Check if is not None because maybe we have already created a new connection on array+1 and now index is None
                for index in range(0, len(self.ws_pool.ws)):
                    if (
                        self.ws_pool.ws[index].is_reconneting is False
                        and self.ws_pool.ws[index].elapsed_last_ping() > 10
                        and internet_connection_available() is True
                    ):
                        logger.info(
                            f"#{index} - The last PING was sent more than 10 minutes ago. Reconnecting to the WebSocket..."
                        )
                        WebSocketsPool.handle_reconnection(self.ws_pool.ws[index])

    def end(self, signum, frame):
        logger.info("CTRL+C Detected! Please wait just a moment!")

        self.running = self.twitch.running = False
        self.ws_pool.end()

        self.minute_watcher_thread.join()
        time.sleep(1)

        self.__print_report()

        sys.exit(0)

    def __print_report(self):
        print("\n")
        logger.info(
            f"Ending session: '{self.session_id}'", extra={"emoji": ":stop_sign:"}
        )
        if self.logs_file is not None:
            logger.info(
                f"Logs file: {self.logs_file}", extra={"emoji": ":page_facing_up:"}
            )
        logger.info(
            f"Duration {datetime.now() - self.start_datetime}",
            extra={"emoji": ":hourglass:"},
        )

        if self.events_predictions != {}:
            print("")
            for event_id in self.events_predictions:
                if (
                    self.events_predictions[event_id].bet_confirmed is True
                    and self.events_predictions[
                        event_id
                    ].streamer.settings.make_predictions
                    is True
                ):
                    logger.info(
                        f"{self.events_predictions[event_id].streamer.settings.bet}",
                        extra={"emoji": ":wrench:"},
                    )
                    if (
                        self.events_predictions[
                            event_id
                        ].streamer.settings.bet.filter_condition
                        is not None
                    ):
                        logger.info(
                            f"{self.events_predictions[event_id].streamer.settings.bet.filter_condition}",
                            extra={"emoji": ":pushpin:"},
                        )
                    logger.info(
                        f"{self.events_predictions[event_id].print_recap()}",
                        extra={"emoji": ":bar_chart:"},
                    )

        print("")
        for streamer_index in range(0, len(self.streamers)):
            if self.streamers[streamer_index].history != {}:
                logger.info(
                    f"{repr(self.streamers[streamer_index])}, Total Points Gained (after farming - before farming): {_millify(self.streamers[streamer_index].channel_points - self.original_streamers[streamer_index].channel_points)}",
                    extra={"emoji": ":robot:"},
                )
                if self.streamers[streamer_index].history != {}:
                    logger.info(
                        f"{self.streamers[streamer_index].print_history()}",
                        extra={"emoji": ":moneybag:"},
                    )
