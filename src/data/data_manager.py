import os
import csv
import re
from data.player import Player
from utils.config import load_config, get_project_root
from utils.utils import parse_game_time
from datetime import datetime, timedelta
import pytz
import itertools


class DataManager:
    def __init__(self, site):
        self.site = site
        self.config = load_config(site)
        self.players = []
        self.rename_dict = {
            "Nicolas Claxton": "Nic Claxton",
            "Royce O'Neale": "Royce O'neale",
            # ownership.csv: projections.csv
        }
        self.lineups = []
        self.ids_to_gametime = {}
        self.eastern = pytz.timezone("US/Eastern")


    def _resolve_path(self, relative_path):
        """
        Resolve a relative path to an absolute path based on the project root.
        :param relative_path: The relative path from the config file.
        :return: The absolute path.
        """
        return os.path.join(get_project_root(), relative_path)
    
    def populate_ids_to_gametime(self):
        """
        Populate the ids_to_gametime dictionary with timezone-aware datetimes,
        adjusting the lock time to be one hour earlier than the actual game time.
        """
        self.ids_to_gametime = {
            player.id: player.gametime
            for player in self.players
            if hasattr(player, "id") and hasattr(player, "gametime") and player.id and player.gametime
        }
        print(f"Populated ids_to_gametime with {len(self.ids_to_gametime)} entries, adjusted lock time by -1 hour.")



    
    def load_player_data(self):
        """
        Load all player data based on their presence in the player_ids.csv file.
        Populate additional data such as projections, ownership, and boom-bust values.
        """
        # First initialize players from player_ids.csv
        self._initialize_players_from_ids(self._resolve_path(self.config["player_path"]))

        # Populate additional data for players
        self._load_projections(self._resolve_path(self.config["projection_path"]))
        self._load_boom_bust(self._resolve_path(self.config["boom_bust_path"]))
        self._load_ownership(self._resolve_path(self.config["ownership_path"]))


    def _load_projections(self, path):
        """
        Add projections data to the initialized players.
        """
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                positions = row["Position"].split("/")
                if self.site == "dk":
                    if "PG" in positions or "SG" in positions:
                        positions.append("G")
                    if "SF" in positions or "PF" in positions:
                        positions.append("F")
                    positions.append("UTIL")

                matched = False
                for player in self.players:
                    if player.name == row["Name"].strip() and player.team == row["Team"]:
                        player.fpts = float(row["Fpts"])
                        player.minutes = float(row["Minutes"])
                        player.position = positions
                        matched = True
                        break
                
                if not matched:
                    print(f"Warning: No matching player found for {row['Name']} on team {row['Team']}")


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
        # Load ownership file and check against players
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                ownership_name = row["Name"].strip()
                
                # Check if the player's name is in the rename_dict
                if ownership_name in self.rename_dict:
                    ownership_name = self.rename_dict[ownership_name]  # Use the new name

                # Match against players and update ownership
                for player in self.players:
                    if player.name == ownership_name and player.team == row["Team"]:
                        player.ownership = float(row["Ownership %"])
                        break


    def _initialize_players_from_ids(self, path):
        """
        Initialize Player objects based on player_ids.csv.
        """
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    gametime = parse_game_time(row["Game Info"])
                except ValueError as e:
                    print(f"Skipping player {row['Name']} due to game info error: {e}")
                    gametime = None

                player = Player(
                    name=row["Name"].strip(),
                    team=row["TeamAbbrev"],
                    id=row["ID"],
                    gametime=gametime, 
                    salary=int(row["Salary"].replace(",", ""))
                )
                self.players.append(player)
        print(f"Initialized {len(self.players)} players from player_ids.csv.")


    def load_player_lineups(self, path):
        """
        Load player lineups from a CSV file, ensuring that current time is correctly converted to match EST.
        """
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(self.lower_first(file))

            # Convert current time to EST
            current_time = datetime.now(pytz.timezone("US/Central"))  # Get current time in CST
            current_time = current_time.astimezone(self.eastern)  # Convert to EST
            print(f"Current time (ET): {current_time}")

            for row in reader:
                if row["entry id"] != "" and self.site == "dk":
                    # Extract player IDs from the lineup
                    PG_id = re.search(r"\((\d+)\)", row["pg"]).group(1)
                    SG_id = re.search(r"\((\d+)\)", row["sg"]).group(1)
                    SF_id = re.search(r"\((\d+)\)", row["sf"]).group(1)
                    PF_id = re.search(r"\((\d+)\)", row["pf"]).group(1)
                    C_id = re.search(r"\((\d+)\)", row["c"]).group(1)
                    G_id = re.search(r"\((\d+)\)", row["g"]).group(1)
                    F_id = re.search(r"\((\d+)\)", row["f"]).group(1)
                    UTIL_id = re.search(r"\((\d+)\)", row["util"]).group(1)

                    # Print comparison times for each player
                    for position, player_id in zip(
                        ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"],
                        [PG_id, SG_id, SF_id, PF_id, C_id, G_id, F_id, UTIL_id]
                    ):
                        if player_id in self.ids_to_gametime:
                            player_time = self.ids_to_gametime[player_id]
                            print(f"{position} ({player_id}): Current Time: {current_time}, Game Time: {player_time}")
                        else: 
                            print(f"{position} ({player_id}):  not found in ids_to_gametime")

                    # Add lineup data, including lock status
                    self.lineups.append(
                        {
                            "Entry ID": row["entry id"],
                            "Contest ID": row["contest id"],
                            "Contest Name": row["contest name"],
                            "Entry Fee": row["entry fee"],
                            "PG": row["pg"].replace("-", "#"),
                            "SG": row["sg"].replace("-", "#"),
                            "SF": row["sf"].replace("-", "#"),
                            "PF": row["pf"].replace("-", "#"),
                            "C": row["c"].replace("-", "#"),
                            "G": row["g"].replace("-", "#"),
                            "F": row["f"].replace("-", "#"),
                            "UTIL": row["util"].replace("-", "#"),
                            "PG_is_locked": (
                                current_time > self.ids_to_gametime[PG_id]
                                if PG_id in self.ids_to_gametime
                                else False
                            ),
                            "SG_is_locked": (
                                current_time > self.ids_to_gametime[SG_id]
                                if SG_id in self.ids_to_gametime
                                else False
                            ),
                            "SF_is_locked": (
                                current_time > self.ids_to_gametime[SF_id]
                                if SF_id in self.ids_to_gametime
                                else False
                            ),
                            "PF_is_locked": (
                                current_time > self.ids_to_gametime[PF_id]
                                if PF_id in self.ids_to_gametime
                                else False
                            ),
                            "C_is_locked": (
                                current_time > self.ids_to_gametime[C_id]
                                if C_id in self.ids_to_gametime
                                else False
                            ),
                            "G_is_locked": (
                                current_time > self.ids_to_gametime[G_id]
                                if G_id in self.ids_to_gametime
                                else False
                            ),
                            "F_is_locked": (
                                current_time > self.ids_to_gametime[F_id]
                                if F_id in self.ids_to_gametime
                                else False
                            ),
                            "UTIL_is_locked": (
                                current_time > self.ids_to_gametime[UTIL_id]
                                if UTIL_id in self.ids_to_gametime
                                else False
                            ),
                        }
                    )
        print(f"Successfully loaded {len(self.lineups)} lineups for late swap.")



    def lower_first(self, iterator):
        return itertools.chain([next(iterator).lower()], iterator)



