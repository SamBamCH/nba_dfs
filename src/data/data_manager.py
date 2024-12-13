import os
import csv
from data.player import Player
from utils.config import load_config, get_project_root
from datetime import datetime


class DataManager:
    def __init__(self, site):
        self.site = site
        self.config = load_config(site)
        self.players = []

    def _resolve_path(self, relative_path):
        """
        Resolve a relative path to an absolute path based on the project root.
        :param relative_path: The relative path from the config file.
        :return: The absolute path.
        """
        return os.path.join(get_project_root(), relative_path)

    def load_player_data(self):
        """
        Load all player data from projections, ownership, and boom-bust files.
        """
        self._load_projections(self._resolve_path(self.config["projection_path"]))
        self._load_boom_bust(self._resolve_path(self.config["boom_bust_path"]))
        self._load_ownership(self._resolve_path(self.config["ownership_path"]))
        self._load_player_ids(self._resolve_path(self.config["player_path"]))

    def _load_projections(self, path):
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                fpts = float(row["Fpts"])
                if fpts >= self.config["projection_minimum"]:
                    # Split positions and append G, F, UTIL for DraftKings
                    positions = row["Position"].split("/")
                    if self.site == "dk":
                        if "PG" in positions or "SG" in positions:
                            positions.append("G")
                        if "SF" in positions or "PF" in positions:
                            positions.append("F")
                        positions.append("UTIL")

                    player = Player(
                        name=row["Name"].strip(),
                        team=row["Team"],
                        position=positions,
                        salary=int(row["Salary"].replace(",", "")),
                        fpts=fpts,
                        minutes=float(row["Minutes"])
                    )
                    self.players.append(player)

    def _load_boom_bust(self, path):
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                for player in self.players:
                    if player.name == row["Name"].strip() and player.team == row["Team"]:
                        player.ceiling = float(row["Ceiling"])
                        player.boom_pct = float(row["Boom%"])
                        player.bust_pct = float(row["Bust%"])
                        player.stddev = float(row["Std Dev"])
                        break

    def _load_ownership(self, path):
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                for player in self.players:
                    if player.name == row["Name"].strip() and player.team == row["Team"]:
                        player.ownership = float(row["Ownership %"])
                        break

    def _load_player_ids(self, path):
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                for player in self.players:
                    if player.name == row["Name"].strip() and player.team == row["TeamAbbrev"]:
                        player.id = int(row["ID"])
                        game_info = row["Game Info"]
                        try:
                            # Split Game Info to extract date and time, handle "ET"
                            date_part, time_part, _ = game_info.split()[-3:]
                            player.gametime = datetime.strptime(
                                f"{date_part} {time_part}", "%m/%d/%Y %I:%M%p"
                            )
                        except ValueError as e:
                            raise ValueError(f"Error parsing Game Info '{game_info}' for player {player.name}: {e}")
                        break

