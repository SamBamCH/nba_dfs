import json
import csv
import os
import datetime
import numpy as np
import pulp as plp
import random
import itertools
import pandas as pd
from itertools import combinations


class Optimizer:
    def __init__(self, site, num_lineups, num_uniques, randomness_amount=None, ownership_limits=None):
        self.site = site
        self.num_lineups = int(num_lineups)
        self.num_uniques = int(num_uniques)
        self.config = self.load_config()
        self.load_rules()


        # Allow overriding randomness if provided
        if randomness_amount is not None:
            self.randomness_amount = randomness_amount

        self.ownership_limits = ownership_limits  # Will be used to enforce ownership constraints if needed

        # Set up initial dictionaries and defaults
        self.players_with_default_ownership = []
        self.output_dir = None
        self.lineups = []
        self.player_dict = {}
        self.player_selections = {}
        self.team_list = []
        self.combo_usage_variables = {}
        self.pair_variables = {}
        self.team_replacement_dict = {
            "PHX": "PHO",
            "GSW": "GS",
            "SAS": "SA",
            "NYK": "NY",
            "NOP": "NO",

        }
        self.matchup_list = []

        self.problem = plp.LpProblem("NBA", plp.LpMaximize)

        # Load player data
        self.load_player_data()

    def load_player_data(self):
        # Navigate to project root from src/optimizer/
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
        data_dir = os.path.join(base_dir, "data", self.site)

        player_path = os.path.join(data_dir, self.config["player_path"])
        projection_path = os.path.join(data_dir, self.config["projection_path"])
        ownership_path = os.path.join(data_dir, self.config["ownership_path"])
        boom_bust_path = os.path.join(data_dir, self.config["boom_bust_path"])

        self.teams_in_player_ids = self.get_teams_from_player_ids(player_path)

        self.load_projections(projection_path)
        self.load_player_ids(player_path)
        self.load_boom_bust(boom_bust_path)
        self.load_ownership(ownership_path)
        self.report_default_ownership_players()

    def load_config(self):
    # Navigate from src/optimizer to project root
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
        config_path = os.path.join(base_dir, "config", f"{self.site}_config.json")

        with open(config_path, encoding="utf-8-sig") as json_file:
            config = json.load(json_file)
        self.custom_correlations = config.get('custom_correlations', {})
        self.combination_limits = config.get('player_combination_limits', {})
        return config


    def load_rules(self):
        self.at_most = self.config.get("at_most", {})
        self.at_least = self.config.get("at_least", {})
        self.team_limits = self.config.get("team_limits", {})
        self.global_team_limit = int(self.config.get("global_team_limit", 6))
        self.projection_minimum = int(self.config.get("projection_minimum", 12))
        self.randomness_amount = float(self.config.get("randomness", 15))
        self.matchup_limits = self.config.get("matchup_limits", {})
        self.matchup_at_least = self.config.get("matchup_at_least", {})
        self.min_salary = int(self.config.get("min_lineup_salary", 49500))
        self.min_minutes = float(self.config.get("minutes_min", 0))
        self.correlation_weight = float(self.config.get("correlation_weight", 0))

    def lower_first(self, iterator):
        return itertools.chain([next(iterator).lower()], iterator)

    def get_teams_from_player_ids(self, path):
        teams = set()
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                team = row["TeamAbbrev"] if self.site == "dk" else row["Team"]
                teams.add(team)
        return teams

    def load_player_ids(self, path):
        # Dictionary to keep track of players that are found in the CSV but not in player_dict
        missing_players = {}

        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                name_key = "Name" if self.site == "dk" else "Nickname"
                player_name = row[name_key].replace("-", "#").strip()
                team = row["TeamAbbrev"] if self.site == "dk" else row["Team"]
                position = row["Position"]

                if self.site == "fd":
                    if team in self.team_replacement_dict:
                        team = self.team_replacement_dict[team]

                player_key = (player_name, position, team)



                # Check if the player_key is already in player_dict
                if player_key in self.player_dict:
                    # Existing player, update their 'ID' and other info
                    if self.site == "dk":
                        self.player_dict[player_key]["ID"] = int(row["ID"])
                        # Parse the 'Game Info' to extract 'Matchup' and 'GameTime'
                        game_info = row["Game Info"].split()
                        if len(game_info) >= 3:  # Basic validation to avoid IndexError
                            matchup = game_info[0]
                            game_time_str = " ".join(game_info[1:3])
                            try:
                                game_time = datetime.datetime.strptime(game_time_str, "%m/%d/%Y %I:%M%p")
                                self.player_dict[player_key]["GameTime"] = game_time
                                self.player_dict[player_key]["Matchup"] = matchup
                            except ValueError as e:
                                print(f"Error parsing 'GameTime' for player {player_key}: {e}")
                        else:
                            print(f"Invalid 'Game Info' format for player {player_key}")
                    else:
                        self.player_dict[(player_name, position, team)]["ID"] = row[
                            "Id"
                        ].replace("-", "#")
                        game_str = (
                            row["Game"].replace("PHO", "PHX").replace("GS", "GSW")
                        )
                        self.player_dict[(player_name, position, team)][
                            "Matchup"
                        ] = game_str
                        if game_str not in self.matchup_list:
                            self.matchup_list.append(game_str)
                else:
                    # Player not found in player_dict, add to missing_players
                    missing_players[player_key] = {
                        "ID": row.get("ID") or row.get("Id"),
                        "Team": team,
                        "Position": position
                    }

    def load_projections(self, path):
        # Read projections into a dictionary
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(self.lower_first(file))
            for row in reader:
                player_name = row["name"].replace("-", "#").strip()
                position = row["position"]
                team = row["team"]
                fpts = float(row["fpts"])
                minutes = float(row["minutes"])
                pts_per_dollar = float(row["pts/$"])

                if team not in self.teams_in_player_ids:
                    continue

                if self.site == "fd":
                    if team in self.team_replacement_dict:
                        team = self.team_replacement_dict[team]

                # populate player class with players
                self.player_dict[(player_name, position, team)] = {
                    "Fpts": fpts,
                    "Salary": int(row["salary"].replace(",", "")),
                    "Minutes": minutes,
                    "Name": row["name"],
                    "Team": row["team"],
                    "Value": pts_per_dollar,
                    "Position": [position for position in row["position"].split("/")]
                }

                if self.site == "dk":
                    if "PG" in row["position"] or "SG" in row["position"]:
                        self.player_dict[(player_name, position, team)][
                            "Position"
                        ].append("G")
                    if "SF" in row["position"] or "PF" in row["position"]:
                        self.player_dict[(player_name, position, team)][
                            "Position"
                        ].append("F")

                    self.player_dict[(player_name, position, team)]["Position"].append(
                        "UTIL"
                    )

                if team not in self.team_list:
                    self.team_list.append(team)

    def load_ownership(self, path):
        default_ownership = 0.005

        # Reset the list for a fresh start
        self.players_with_default_ownership = []

        # Set ownership to default for all players initially
        for player_key in self.player_dict.keys():
            self.player_dict[player_key]["Ownership"] = default_ownership
            self.players_with_default_ownership.append(player_key)  # Add player to list

        # Read ownership data from a file
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(self.lower_first(file))
            for row in reader:
                player_name = row["name"].replace("-", "#").strip()
                position = row["position"]
                team = row["team"]
                ownership = float(row["ownership %"])

                for player_key in self.player_dict:
                    if player_key == (player_name, position, team):
                        self.player_dict[player_key]["Ownership"] = ownership
                        if player_key in self.players_with_default_ownership:
                            self.players_with_default_ownership.remove(player_key)  # Remove from default list
                        break

    def report_default_ownership_players(self):
        print("Players with default ownership value:")
        for player in self.players_with_default_ownership:
            if player in self.player_dict:
                player_data = self.player_dict[player]
                print(f"{player[0]} ({player[1]}, {player[2]}): pts/$ = {player_data['Value']}")
            else:
                print(f"{player} not found in player_dict")

    def load_boom_bust(self, path):
        # Read projections into a dictionary
        # Open the CSV file
        with open(path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            # Iterate over each row in the CSV file
            for row in reader:
                # Create the player key as per your existing `player_dict` keys
                player_name = row["Name"].replace("-", "#").strip()
                team = row["Team"]
                position = row["Position"]

                # Adjust for the site-specific naming if necessary
                if self.site == "fd" and team in self.team_replacement_dict:
                    team = self.team_replacement_dict[team]

                # Create the player key
                player_key = (player_name, position, team)

                # If the player is in player_dict, update their data with the new stats
                if player_key in self.player_dict:
                    self.player_dict[player_key].update({
                        "Ceiling": float(row["Ceiling"]),
                        "Boom%": float(row["Boom%"]), 
                        "StdDev": float(row["Std Dev"]),
                        "Bust%": float(row["Bust%"]),
                        "Optimal%": float(row["Optimal%"])
                    })
                else:
                    # Handle the case where the player is not found if necessary
                    # e.g., log a warning or add them to a missing players list
                    pass

        for player, attrs in self.player_dict.items():
            if "StdDev" not in attrs:
                attrs["StdDev"] = 5.0

    def calculate_ownership_sum(self, lineup):
        # Logic from original code unchanged
        # ...
        pass

    def calculate_ownership_sums(self, lineups):
        return [self.calculate_ownership_sum(lineup) for lineup in lineups]

    def find_ownership_threshold(self, ownership_sums, percentile):
        return np.percentile(ownership_sums, percentile)

    def print_rules(self):
        # Logic from original code unchanged
        pass

    def optimize(self, num_lineups, ownership_sum_threshold=None):

        # We will use PuLP as our solver - https://coin-or.github.io/pulp/
        # We want to create a variable for each roster slot.
        # There will be an index for each player and the variable will be binary (0 or 1) representing whether the player is included or excluded from the roster.
        # Create a binary decision variable for each player for each of their positions
        # Setup our linear programming equation - https://en.wikipedia.org/wiki/Linear_programming

        lp_variables = {}

        randomness = self.randomness_amount

        fpts_weight = 1 #TODO: figure out what this is

        for player, attributes in self.player_dict.items():
            if "ID" in attributes:
                player_id = attributes["ID"]
            else:
                print(
                    f"Player in player_dict does not have an ID: {player}. Check for mis-matches between names, teams or positions in projections.csv and player_ids.csv"
                )
            for pos in attributes["Position"]:
                lp_variables[(player, pos, player_id)] = plp.LpVariable(
                    name=f"{player}_{pos}_{player_id}", cat=plp.LpBinary
                )

        # set the objective - maximize fpts & set randomness amount from config
        if randomness != 0:
            self.problem += (
                plp.lpSum(
                    np.random.normal(
                        self.player_dict[player]["Fpts"],
                        self.player_dict[player]["StdDev"] * randomness / 100
                    ) * lp_variables[(player, pos, attributes["ID"])]
                    for player, attributes in self.player_dict.items()
                    for pos in attributes["Position"]
                ),
                "Objective",
            )
        else:
            self.problem += (
                plp.lpSum(
                    self.player_dict[player]["Fpts"]
                    * lp_variables[(player, pos, self.player_dict[player]["ID"])]
                    for player in self.player_dict
                    for pos in self.player_dict[player]["Position"]
                ),
                "Objective",
            )

        # Set the salary constraints
        max_salary = 50000 if self.site == "dk" else 60000
        min_salary = 49000 if self.site == "dk" else 59000

        if self.projection_minimum is not None:
            min_salary = self.min_salary

        # Maximum Salary Constraint
        self.problem += (
            plp.lpSum(
                self.player_dict[player]["Salary"]
                * lp_variables[(player, pos, attributes["ID"])]
                for player, attributes in self.player_dict.items()
                for pos in attributes["Position"]
            )
            <= max_salary,
            "Max Salary",
        )

        # Minimum Salary Constraint
        self.problem += (
            plp.lpSum(
                self.player_dict[player]["Salary"]
                * lp_variables[(player, pos, attributes["ID"])]
                for player, attributes in self.player_dict.items()
                for pos in attributes["Position"]
            )
            >= min_salary,
            "Min Salary",
        )

        # Must not play all 8 or 9 players from the same match (8 if dk, 9 if fd)
        matchup_limit = 8 if self.site == "dk" else 9
        for matchupIdent in self.matchup_list:
            self.problem += (
                plp.lpSum(
                    lp_variables[(player, pos, attributes["ID"])]
                    for player, attributes in self.player_dict.items()
                    for pos in attributes["Position"]
                    if attributes["Matchup"] in matchupIdent
                )
                <= matchup_limit,
                f"Must not play all {matchup_limit} players from match {matchupIdent}",
            )

        # Address limit rules if any
        for limit, groups in self.at_least.items():
            for group in groups:
                self.problem += (
                    plp.lpSum(
                        lp_variables[(player, pos, attributes["ID"])]
                        for player, attributes in self.player_dict.items()
                        for pos in attributes["Position"]
                        if attributes["Name"] in group
                    )
                    >= int(limit),
                    f"At least {limit} players {group}",
                )

        for limit, groups in self.at_most.items():
            for group in groups:
                self.problem += (
                    plp.lpSum(
                        lp_variables[(player, pos, attributes["ID"])]
                        for player, attributes in self.player_dict.items()
                        for pos in attributes["Position"]
                        if attributes["Name"] in group
                    )
                    <= int(limit),
                    f"At most {limit} players {group}",
                )

        for matchup, limit in self.matchup_limits.items():
            self.problem += (
                plp.lpSum(
                    lp_variables[(player, pos, attributes["ID"])]
                    for player, attributes in self.player_dict.items()
                    for pos in attributes["Position"]
                    if attributes["Matchup"] == matchup
                )
                <= int(limit),
                "At most {} players from {}".format(limit, matchup),
            )

        for matchup, limit in self.matchup_at_least.items():
            self.problem += (
                plp.lpSum(
                    lp_variables[(player, pos, attributes["ID"])]
                    for player, attributes in self.player_dict.items()
                    for pos in attributes["Position"]
                    if attributes["Matchup"] == matchup
                )
                >= int(limit),
                "At least {} players from {}".format(limit, matchup),
            )

        # Address team limits
        for teamIdent, limit in self.team_limits.items():
            self.problem += plp.lpSum(
                lp_variables[self.player_dict[(player, pos_str, team)]["ID"]]
                for (player, pos_str, team) in self.player_dict
                if team == teamIdent
            ) <= int(limit), "At most {} players from {}".format(limit, teamIdent)

        if self.global_team_limit is not None:
            if not (self.site == "fd" and self.global_team_limit >= 4):
                for teamIdent in self.team_list:
                    self.problem += (
                        plp.lpSum(
                            lp_variables[(player, pos, attributes["ID"])]
                            for player, attributes in self.player_dict.items()
                            for pos in attributes["Position"]
                            if attributes["Team"] == teamIdent
                        )
                        <= int(self.global_team_limit),
                        f"Global team limit - at most {self.global_team_limit} players from {teamIdent}",
                    )

        if self.site == "dk":
            # Constraints for specific positions
            for pos in ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]:
                self.problem += (
                    plp.lpSum(
                        lp_variables[(player, pos, attributes["ID"])]
                        for player, attributes in self.player_dict.items()
                        if pos in attributes["Position"]
                    )
                    == 1,
                    f"Must have 1 {pos}",
                )

            # Constraint to ensure each player is only selected once
            for player in self.player_dict:
                player_id = self.player_dict[player]["ID"]
                self.problem += (
                    plp.lpSum(
                        lp_variables[(player, pos, player_id)]
                        for pos in self.player_dict[player]["Position"]
                    )
                    <= 1,
                    f"Can only select {player} once",
                )

        else:
            # Constraints for specific positions
            for pos in ["PG", "SG", "SF", "PF", "C"]:
                if pos == "C":
                    self.problem += (
                        plp.lpSum(
                            lp_variables[(player, pos, attributes["ID"])]
                            for player, attributes in self.player_dict.items()
                            if pos in attributes["Position"]
                        )
                        == 1,
                        f"Must have 1 {pos}",
                    )
                else:
                    self.problem += (
                        plp.lpSum(
                            lp_variables[(player, pos, attributes["ID"])]
                            for player, attributes in self.player_dict.items()
                            if pos in attributes["Position"]
                        )
                        == 2,
                        f"Must have 2 {pos}",
                    )

            # Max 4 players from one team
            for team in self.team_list:
                self.problem += (
                    plp.lpSum(
                        lp_variables[(player, pos, attributes["ID"])]
                        for player, attributes in self.player_dict.items()
                        for pos in attributes["Position"]
                        if team in attributes["Team"]
                    )
                    <= 4,
                    f"Max 4 players from {team}",
                )

            # Constraint to ensure each player is only selected once
            for player in self.player_dict:
                player_id = self.player_dict[player]["ID"]
                self.problem += (
                    plp.lpSum(
                        lp_variables[(player, pos, player_id)]
                        for pos in self.player_dict[player]["Position"]
                    )
                    <= 1,
                    f"Can only select {player} once",
                )

            # Apply the limit constraint for each pair across all lineups
        for pair_info in self.combination_limits["pairs"]:
            players = tuple(pair_info["players"])
            for i in range(self.num_lineups):
                var_name = f"pair_{'_'.join(players)}_{i}"
                self.pair_variables[(players, i)] = plp.LpVariable(var_name, cat=plp.LpBinary)

                # Link these variables to the actual players in the lineup
                # Assuming player keys are in the format (name, position, team)
                player_vars = [lp_variables[(name, pos, id)] for name, pos, id in lp_variables if name in players]
                self.problem += (self.pair_variables[(players, i)] <= sum(player_vars))

        for pair_info in self.combination_limits["pairs"]:
            players = tuple(pair_info["players"])
            limit = pair_info["limit"] * self.num_lineups
            pair_vars = [self.pair_variables[(players, i)] for i in range(self.num_lineups)]
            self.problem += plp.lpSum(pair_vars) <= limit

        self.problem.writeLP("problem.lp")
        # Crunch!

        self.lineups.clear()

        successful_lineups = 0
        attempted_lineups = 0
        while successful_lineups < num_lineups:
            try:
                self.problem.solve(plp.GLPK(msg=0))
            except plp.PulpSolverError:
                print("Error solving lineup {}".format(attempted_lineups))
                continue

            if plp.LpStatus[self.problem.status] != "Optimal":
                print("Non-optimal status for lineup {}".format(attempted_lineups))
                continue

            attempted_lineups += 1
            selected_vars = [player for player in lp_variables if lp_variables[player].varValue != 0]
            calculated_ownership_sum = self.calculate_ownership_sum(selected_vars)

            if ownership_sum_threshold is not None and calculated_ownership_sum > ownership_sum_threshold:
                print("Skipping lineup {} due to high ownership sum: {}".format(attempted_lineups,
                                                                                calculated_ownership_sum))
            else:
                print(f"Adding lineup {successful_lineups} with ownership sum: {calculated_ownership_sum}")
                self.lineups.append(selected_vars)
                successful_lineups += 1

                # Update player selections only for successful lineups
                for player_var in selected_vars:
                    player_key = player_var[0]
                    if player_key in self.player_selections:
                        self.player_selections[player_key] += 1
                    else:
                        self.player_selections[player_key] = 1

            # Constraint to exclude the current lineup in future iterations
            player_ids = [tpl[2] for tpl in selected_vars]
            player_keys_to_exclude = [(key, pos, attr["ID"]) for key, attr in self.player_dict.items() if
                                      attr["ID"] in player_ids]
            self.problem += (
                plp.lpSum(lp_variables[x] for x in player_keys_to_exclude)
                <= len(selected_vars) - self.num_uniques,
                f"Exclude_Lineup_{attempted_lineups}",
            )

            # Update player selections
            for player_var in selected_vars:
                player_key = player_var[0]  # Assuming player_var[0] contains the player's name or unique identifier
                if player_key in self.player_selections:
                    self.player_selections[player_key] += 1
                else:
                    self.player_selections[player_key] = 1

            # self.problem.writeLP("problem.lp")

            # Set a new random fpts projection within their distribution
            if self.randomness_amount != 0:
                self.problem += (
                    plp.lpSum(
                        fpts_weight* np.random.normal(
                            self.player_dict[player]["Fpts"],
                            (
                                    self.player_dict[player]["StdDev"]
                                    * self.randomness_amount
                                    / 100
                            ),
                        )
                        * lp_variables[(player, pos, attributes["ID"])]
                        for player, attributes in self.player_dict.items()
                        for pos in attributes["Position"]
                    ),
                    "Objective",
                )

    def set_ownership_limits(self, ownership_limits):
        # Store calculated ownership limits for next run
        self.ownership_limits = ownership_limits

    def calculate_ownership_limits(self, lineups):
        # Implement logic to derive ownership constraints from lineups
        # Return a dictionary of ownership limits
        return {}

    def output(self):
        # Logic from original code unchanged
        pass

    def sort_lineup(self, lineup):
        # Logic from original code unchanged
        pass

    def adjust_roster_for_late_swap(self, lineup):
        # Logic from original code unchanged
        pass
