#!/usr/bin/env python3
#
# Listen to radio stations.

import argparse
import json
import os
import re
import requests
import subprocess

from collections import defaultdict

import bs4
import click

from fuzzyfinder import fuzzyfinder
from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion


__version__ = "0.1.0"

# Json file to store radios urls.
RADIO_STATIONS_FILE = "radio_stations.json"
HISTORY_FILE = "history.txt"

PROMPT = "radioGaGa > "
USER_INPUT_PATTERN = re.compile(r"\s*(?P<command>[^\s]+)\s+(?P<station>.*)$")

URL_RADIO_STATIONS_LIST_FR = "https://doc.ubuntu-fr.org/liste_radio_france"
URL_PATTERN = re.compile(r"https?://")

EXCLUDE_HREF_PATTERNS = [re.compile(r"[^A-Za-z0-9]lofi[^A-Za-z0-9]")]

DEFAULT_MEDIA_PLAYER = "mpv"
MEDIA_PLAYERS_DEFAULT_ARGS = {"mpv": "--no-video", "vlc": ""}


class RadioCompleter(Completer):
    """
    """

    def __init__(self, commands, stations):
        super().__init__()
        self.commands = commands
        self.stations = stations

    def get_completions(self, document, complete_event):
        text_before_cursor = document.current_line_before_cursor
        text_before_cursor_stripped = text_before_cursor.lstrip()

        if " " in text_before_cursor:
            # We got past the command and start looking for radio stations
            stripped_len = len(text_before_cursor) - len(text_before_cursor_stripped)
            command = text_before_cursor.split()[0]
            if command in self.commands:
                offset_stations_string = stripped_len + len(command) + 1  # Adds 1 to skip space after command.
                search_for = text_before_cursor[offset_stations_string:]

                matches = fuzzyfinder(search_for, list(self.stations))
                for m in matches:
                    yield Completion(
                        m, -(document.cursor_position - offset_stations_string), display_meta=self.stations[m]
                    )
        else:
            word_before_cursor = document.get_word_before_cursor(WORD=True)
            matches = fuzzyfinder(word_before_cursor, self.commands)
            for m in matches:
                yield Completion(m, start_position=-len(word_before_cursor))


def parse_args():
    """
    """
    parser = argparse.ArgumentParser(description="Radio player CLI.")

    parser.add_argument(
        "-f",
        "--stations-file",
        action="store",
        dest="stations_file",
        default=RADIO_STATIONS_FILE,
        help="Loads radio stations from specified json file",
    )
    parser.add_argument(
        "-r",
        "--refresh",
        "--refresh-stations",
        dest="refresh",
        action="store_true",
        help="Refresh radio stations url. Edits in place the file specified with '-f' options.",
    )
    parser.add_argument(
        "-p",
        "--player",
        default=DEFAULT_MEDIA_PLAYER,
        dest="player",
        action="store",
        help="Media player to use to open http[s] audio streams.",
    )

    args = parser.parse_args()
    return args


def load_stations_from_file(filename):
    """
    """
    path = os.path.abspath(filename)
    with open(path, "r", encoding="utf8") as f:
        stations = json.load(f)
    return stations


def save_stations_to_file(stations, filename):
    """ Saves radio stations urls to json file.
    """
    path = os.path.abspath(filename)
    with open(path, "w", encoding="utf8") as f:
        print(f"Saving {len(stations)} stations to {path}")
        json.dump(stations, f, indent=4, ensure_ascii=False)


def download_radio_stations_urls(url, exclude_href_patterns=None):
    """ Downloads radio stations urls from HTML page.
    """
    radio_stations = {}

    html_text = requests.get(URL_RADIO_STATIONS_LIST_FR).text
    soup = bs4.BeautifulSoup(html_text, "html.parser")
    attrs = {"href": URL_PATTERN}

    links = soup.find_all("a", attrs=attrs)

    for link in links:
        if not URL_PATTERN.match(link.text):
            count = 1
            # Every anchor without URL as text should be a station name.
            station = link.text
            continue

        href = link["href"]

        if any(pattern.search(href) for pattern in exclude_href_patterns):
            continue  # Skip this link.

        # Add link to corresponding station.
        if station in radio_stations:
            count += 1
            # If a station has multiple URLs, create a separate entry in dict.
            radio_stations[f"{station} {count}"] = href
        else:
            # radio_stations[station].append(link["href"])
            radio_stations[station] = href

    return radio_stations


def fmt_player_cmd(player, player_args, url):
    """ Format shell command to launch player with radio station url.
    """
    return f"{player} {player_args} {url}"


def command_play(radio_stations, station_name):
    """ Routine for 'play' command.
    """
    if not station_name in radio_stations:
        print(f"Unkwnon station: {station_name}")
        return

    url = radio_stations[station_name]
    cmd_line = fmt_player_cmd(PLAYER, MEDIA_PLAYERS_DEFAULT_ARGS[PLAYER], url).split()
    subprocess.run(cmd_line)


def command_info(radio_stations, station_name):
    """ Routine for 'info' command.
    """
    if not station_name in radio_stations:
        print(f"Unkwnon station: {station_name}")
    else:
        print(f"{station_name}: {radio_stations.get(station_name, 'Unknown')}")


def command_search(radio_stations, station_name):
    """ Routine for 'search' command.
    """
    click.echo_via_pager("\n".join(fuzzyfinder(station_name, list(radio_stations))))


def parse_user_input(user_input):
    """ Parses user input line.

    1st word should be a command.
    All further words should be a station name.

    """
    stripped_user_input = user_input.strip()

    if " " in stripped_user_input:
        splitted_user_input = stripped_user_input.split()
        return splitted_user_input[0], " ".join(splitted_user_input[1:])
    return stripped_user_input, None


def main():
    """
    """
    stations_file = args.stations_file

    # Refresh stations urls if explicitly asked or if there is no file to load stations from.
    if args.refresh or not os.path.isfile(stations_file):
        radio_stations = download_radio_stations_urls(URL_RADIO_STATIONS_LIST_FR, EXCLUDE_HREF_PATTERNS)
        save_stations_to_file(radio_stations, stations_file)
    else:
        radio_stations = load_stations_from_file(stations_file)

    # Used for autocompletion
    # radio_completer = WordCompleter(list(radio_stations), ignore_case=True)
    stations_names = list(radio_stations)

    # REPL
    while True:
        try:
            user_input = prompt(
                PROMPT,
                history=FileHistory(HISTORY_FILE),
                auto_suggest=AutoSuggestFromHistory(),
                completer=RadioCompleter(commands=COMMANDS, stations=radio_stations),
                complete_in_thread=True,
                complete_while_typing=False,
                complete_style=CompleteStyle.MULTI_COLUMN,
            )

            command, station_name = parse_user_input(user_input)
            if command in COMMANDS:
                COMMANDS[command](radio_stations, station_name)
            # else:
            #     print("Unknown command")

        except KeyboardInterrupt:
            continue  # Control-C does not stop execution.
        except EOFError:
            break  # Control-D quits.


if __name__ == "__main__":
    COMMANDS = {
        "play": command_play,
        "listen": command_play,
        "show": command_info,
        "info": command_info,
        "search": command_search,
    }

    args = parse_args()
    PLAYER = args.player
    main()
