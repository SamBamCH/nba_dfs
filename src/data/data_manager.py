import os
import json
import csv
from data.player import Player


class DataManager:
    def __init__(self, config_path, site):
        self.config_path = config_path
        self.site = site
        self.config = self._load_config()
        self.players = []

    def _load_config(self):
        with open(self.config_path, encoding="utf-8-sig") as file:
            return json.load(file)

    def load_player_data(self):
        self._load_projections(self.config["projection_path"])
        self._load_boom_bust(self.config["boom_bust_path"])
        self._load_ownership(self.config["ownership_path"])
        self._load_player_ids(self.config["player_path"])

    def _load_projections(self, path):
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                fpts = float(row["fpts"])
                if fpts >= self.config["projection_minimum"]:
                    player = Player(
                        name=row["name"].strip(),
                        team=row["team"],
                        position=row["position"].split("/"),
                        salary=int(row["salary"].replace(",", "")),
                        fpts=fpts,
                        minutes=float(row["minutes"]),
                        stddev=float(row["stddev"]),
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
                        break

    def _load_ownership(self, path):
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                for player in self.players:
                    if player.name == row["name"].strip() and player.team == row["team"]:
                        player.ownership = float(row["ownership %"])
                        break

    def _load_player_ids(self, path):
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                for player in self.players:
                    if player.name == row["Name"].strip() and player.team == row["TeamAbbrev"]:
                        player.id = int(row["ID"])
                        break
