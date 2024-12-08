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


class ownership_optimizer:
    site = None
    config = None
    problem = None
    output_dir = None
    num_lineups = None
    num_uniques = None
    team_list = []
    lineups = []
    player_dict = {}
    team_replacement_dict = {
        "PHX": "PHO",
        "GSW": "GS",
        "SAS": "SA",
        "NYK": "NY",
        "NOP": "NO",

    }
    at_least = {}
    at_most = {}
    team_limits = {}
    matchup_limits = {}
    matchup_at_least = {}
    matchup_list = []
    global_team_limit = None
    projection_minimum = None
    min_minutes = None
    randomness_amount = 0
    min_salary = None
    correlation_weight = 0

    def __init__(self, site=None, num_lineups=0, num_uniques=1):
        self.site = site
        self.num_lineups = int(num_lineups)
        self.num_uniques = int(num_uniques)
        self.load_config()
        self.load_rules()

        self.players_with_default_ownership = []  # Initialize the list

        self.at_least = {}  # Your hardcoded rules
        self.at_most = {}  # Your hardcoded rules
        self.team_limits = {}  # Your hardcoded rules
        self.global_team_limit = 6  # For example
        self.projection_minimum = 0  # For example
        self.randomness_amount = 15  # For example
        self.matchup_limits = {}  # Your hardcoded rules
        self.matchup_at_least = {}  # Your hardcoded rules
        self.min_salary = 49800  # For example
        self.min_minutes = 0  # For example
        self.correlation_weight = 0  # For example
        self.custom_correlations = {}  # Your hardcoded correlations
        self.combination_limits = {}  # Your hardcoded combination limits

        self.problem = plp.LpProblem("NBA", plp.LpMaximize)

        player_path = os.path.join(
            os.path.dirname(__file__),
            "../{}_data/{}".format(site, self.config["player_path"]),
        )
        self.teams_in_player_ids = self.get_teams_from_player_ids(player_path)

        projection_path = os.path.join(
            os.path.dirname(__file__),
            "../{}_data/{}".format(site, self.config["projection_path"]),
        )
        self.load_projections(projection_path)

        player_path = os.path.join(
            os.path.dirname(__file__),
            "../{}_data/{}".format(site, self.config["player_path"]),
        )
        self.load_player_ids(player_path)
        ownership_path = os.path.join(
            os.path.dirname(__file__),
            "../{}_data/{}".format(site, "ownership.csv"),
        )
        boom_bust_path = os.path.join(
            os.path.dirname(__file__),
            "../{}_data/{}".format(site, "boom_bust.csv"),
        )

        self.load_boom_bust(boom_bust_path)
        self.load_ownership(ownership_path)
        self.report_default_ownership_players()  # Report players with default ownership
        self.player_selections = {}
        self.combination_limits = self.config.get('player_combination_limits', {})
        self.combo_usage_variables = {}  # Initialize the attribute here
        self.pair_variables = {}  # Initialize the attribute here

    def print_rules(self):
        print("Optimization Rules:")
        print(f"Global Team Limit: {self.global_team_limit}")
        print(f"Projection Minimum: {self.projection_minimum}")
        print(f"Randomness Amount: {self.randomness_amount}")
        print(f"Minimum Salary Cap: {self.min_salary}")
        print(f"Minimum Player Minutes: {self.min_minutes}")
        print(f"Correlation Weight: {self.correlation_weight}")

    # Load config from file
    def load_config(self):
        with open(os.path.join(os.path.dirname(__file__), "../config.json"), encoding="utf-8-sig") as json_file:
            self.config = json.load(json_file)
        self.custom_correlations = self.config.get('custom_correlations', {})
        self.combination_limits = self.config.get('player_combination_limits', {})

    # make column lookups on datafiles case insensitive
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

    def calculate_ownership_sum(self, lineup):
        """
        Calculate the sum of ownership percentages for a given lineup.
        """
        total_sum = 0.0
        for player_key in lineup:
            player = self.player_dict.get(player_key[0])
            if player:
                total_sum += player["Ownership"]
        return total_sum

    def calculate_ownership_sums(self, lineups):
        """
        Calculate ownership sums for all lineups.
        """
        return [self.calculate_ownership_sum(lineup) for lineup in lineups]

    def find_ownership_threshold(self, ownership_sums, percentile):
        """
        Find the ownership sum threshold based on the specified percentile.
        """
        return np.percentile(ownership_sums, percentile)

    def load_ownership(self, path):
        default_ownership = 0.5

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

    # Load player IDs for exporting
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

    def load_rules(self):
        self.at_most = self.config["at_most"]
        self.at_least = self.config["at_least"]
        self.team_limits = self.config["team_limits"]
        self.global_team_limit = int(self.config["global_team_limit"])
        self.projection_minimum = int(self.config["projection_minimum"])
        self.randomness_amount = float(self.config["randomness"])
        self.matchup_limits = self.config["matchup_limits"]
        self.matchup_at_least = self.config["matchup_at_least"]
        self.min_salary = int(self.config["min_lineup_salary"])
        self.min_minutes = float(self.config["minutes_min"])

    # Load projections from file
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

                # Rest of the code for including players
                self.player_dict[(player_name, position, team)] = {
                    "Fpts": fpts,
                    "Salary": int(row["salary"].replace(",", "")),
                    "Minutes": minutes,
                    "Name": row["name"],
                    "Team": row["team"],
                    "StdDev": float(row["stddev"]),
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
                        "Boom%": float(row["Boom%"])
                    })
                else:
                    # Handle the case where the player is not found if necessary
                    # e.g., log a warning or add them to a missing players list
                    pass


    # def adjusted_projection(self, player, pos, attributes, lp_variables, selected_vars):
    #     projection = self.player_dict[player]["Fpts"] * lp_variables[(player, pos, attributes["ID"])]
    #     for key_player, correlations in self.custom_correlations.items():
    #         if (key_player, pos, self.player_dict[key_player]["ID"]) in lp_variables:
    #             key_player_in_lineup = lp_variables[(key_player, pos, self.player_dict[key_player]["ID"])].varValue != 0
    #             for correlated_player, correlation_value in correlations.items():
    #                 if player == correlated_player:
    #                     adjusted_correlation_value = correlation_value * self.correlation_weight
    #                     if key_player_in_lineup and correlation_value > 0:
    #                         # Apply positive correlation boost
    #                         projection += adjusted_correlation_value * self.player_dict[key_player]["Fpts"] * \
    #                                       lp_variables[
    #                                           (player, pos, attributes["ID"])]
    #                     elif not key_player_in_lineup and correlation_value < 0:
    #                         # Apply negative correlation boost (convert to positive)
    #                         boost = abs(adjusted_correlation_value)
    #                         projection += boost * self.player_dict[key_player]["Fpts"] * lp_variables[
    #                             (player, pos, attributes["ID"])]
    #     return projection

    def print_exposures(self):
        total_lineups = len(self.lineups)
        print("Player Exposures with Projected Values and Ownership:")

        # Calculate exposures
        exposures_data = []
        for player, count in self.player_selections.items():
            exposure_record = {
                'Player': player,
                'Exposure': (count / total_lineups)*100,
                'Projected Value': self.player_dict[player]["Value"]
            }
            exposures_data.append(exposure_record)

        # Create a DataFrame
        df_exposures = pd.DataFrame(exposures_data)

        # Sort by exposure percentage, highest to lowest
        df_exposures = df_exposures.sort_values(by='Exposure', ascending=False)
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', None)

        # Display the DataFrame in PandasGUI
        print(df_exposures)

    def get_high_exposure_players(self, threshold=10):
        """ Get players with exposure higher than the given threshold. """
        total_lineups = len(self.lineups)
        return [player for player, count in self.player_selections.items() if (count / total_lineups) * 100 > threshold]

    def get_combinations(self, players, combo_size):
        """ Generate all combinations of the given size from the players list. """
        return list(combinations(players, combo_size))

    def calculate_combination_exposure(self, combinations, num_lineups):
        """
        Calculate the exposure of specific player combinations across all generated lineups.

        :param combinations: A list of tuples, where each tuple contains players names representing a combination.
        :param num_lineups: Total number of lineups generated.
        :return: DataFrame with combination exposures.
        """
        # Initialize a dictionary to track the count of each combination
        combination_counts = {combo: 0 for combo in combinations}

        # Iterate through each lineup and count the combinations
        for lineup in self.lineups:
            lineup_players = [var[0] for var in lineup]  # Extract player names from the lineup
            for combo in combinations:
                if all(player in lineup_players for player in combo):
                    combination_counts[combo] += 1

        # Calculate the exposure percentage for each combination
        combination_exposure = {combo: (count / num_lineups) * 100 for combo, count in combination_counts.items()}

        # Create a DataFrame from the exposure data
        df_exposure = pd.DataFrame(list(combination_exposure.items()), columns=['Combination', 'Exposure (%)'])

        # Sort the DataFrame by exposure percentage in descending order and filter by the threshold
        df_exposure = df_exposure.sort_values(by='Exposure (%)', ascending=False)

        return df_exposure

    def print_combination_limits(self):
        combination_limits = self.config.get("player_combination_limits", {})
        for combo_type, combos in combination_limits.items():
            for combo in combos:
                players = combo["players"]
                limit = combo["limit"]
                print(f"{combo_type.capitalize()} - Players: {', '.join(players)}, Limit: {limit}")

    def print_top_150_lineup_exposures(self):
        """
        Calculate and print the exposures of players in the top 150 lineups.
        """
        # Number of lineups to consider
        num_lineups_to_consider = 150

        # Ensure there are enough lineups generated
        total_lineups_generated = len(self.lineups)
        if total_lineups_generated < num_lineups_to_consider:
            print(f"Only {total_lineups_generated} lineups are available.")
            num_lineups_to_consider = total_lineups_generated

        print("Player Exposures in Top 150 Lineups:")

        # Initialize a dictionary to track player selection counts
        player_selections = {}

        # Iterate over the first 150 lineups (or the total number of lineups if fewer than 150)
        for lineup in self.lineups[:num_lineups_to_consider]:
            for player_var in lineup:
                player_key = player_var[0]
                player_selections[player_key] = player_selections.get(player_key, 0) + 1

        # Calculate and print exposures
        exposures_data = []
        for player, count in player_selections.items():
            exposure_record = {
                'Player': player,
                'Exposure': (count / num_lineups_to_consider) * 100,
                'Projected Value': self.player_dict[player]["Value"]
            }
            exposures_data.append(exposure_record)

        # Create a DataFrame for visualization
        df_exposures = pd.DataFrame(exposures_data)
        df_exposures = df_exposures.sort_values(by='Exposure', ascending=False)

        # Display the DataFrame
        print(df_exposures)

    def optimize(self, num_lineups, ownership_sum_threshold=None, adjusted_randomness=None):
        randomness = adjusted_randomness if adjusted_randomness is not None else self.randomness_amount

        fpts_weight = 1
        # Setup our linear programming equation - https://en.wikipedia.org/wiki/Linear_programming
        # We will use PuLP as our solver - https://coin-or.github.io/pulp/

        # We want to create a variable for each roster slot.
        # There will be an index for each player and the variable will be binary (0 or 1) representing whether the player is included or excluded from the roster.
        # Create a binary decision variable for each player for each of their positions

        lp_variables = {}
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

    def output(self):
        print("Lineups done generating. Outputting.")

        sorted_lineups = []
        for lineup in self.lineups:
            sorted_lineup = self.sort_lineup(lineup)
            sorted_lineup = self.adjust_roster_for_late_swap(sorted_lineup)
            sorted_lineups.append(sorted_lineup)

        out_path = os.path.join(
            os.path.dirname(__file__),
            "../output/{}_optimal_lineups_{}.csv".format(
                self.site, datetime.datetime.now().strftime("%Y%m%d_%H%M%S%f")[:20]

            ),
        )
        with open(out_path, "w") as f:
            if self.site == "dk":
                f.write(
                    "PG,SG,SF,PF,C,G,F,UTIL,Salary,Fpts Proj,Minutes,StdDev\n"
                )
                for x in sorted_lineups:
                    salary = sum(self.player_dict[player]["Salary"] for player in x)
                    fpts_p = sum(self.player_dict[player]["Fpts"] for player in x)
                    mins = sum([self.player_dict[player]["Minutes"] for player in x])
                    stddev = sum([self.player_dict[player]["StdDev"] for player in x])
                    lineup_str = "{} ({}),{} ({}),{} ({}),{} ({}),{} ({}),{} ({}),{} ({}),{} ({}),{},{},{},{}".format(
                        self.player_dict[x[0]]["Name"],
                        self.player_dict[x[0]]["ID"],
                        self.player_dict[x[1]]["Name"],
                        self.player_dict[x[1]]["ID"],
                        self.player_dict[x[2]]["Name"],
                        self.player_dict[x[2]]["ID"],
                        self.player_dict[x[3]]["Name"],
                        self.player_dict[x[3]]["ID"],
                        self.player_dict[x[4]]["Name"],
                        self.player_dict[x[4]]["ID"],
                        self.player_dict[x[5]]["Name"],
                        self.player_dict[x[5]]["ID"],
                        self.player_dict[x[6]]["Name"],
                        self.player_dict[x[6]]["ID"],
                        self.player_dict[x[7]]["Name"],
                        self.player_dict[x[7]]["ID"],
                        salary,
                        round(fpts_p, 2),
                        mins,
                        stddev,
                    )
                    f.write("%s\n" % lineup_str)
            else:
                f.write(
                    "PG,PG,SG,SG,SF,SF,PF,PF,C,Salary,Fpts Proj,Minutes,StdDev\n"
                )
                for x in sorted_lineups:
                    salary = sum(self.player_dict[player]["Salary"] for player in x)
                    fpts_p = sum(self.player_dict[player]["Fpts"] for player in x)
                    mins = sum([self.player_dict[player]["Minutes"] for player in x])
                    stddev = sum([self.player_dict[player]["StdDev"] for player in x])
                    lineup_str = "{}:{},{}:{},{}:{},{}:{},{}:{},{}:{},{}:{},{}:{},{}:{},{},{},{},{}".format(
                        self.player_dict[x[0]]["ID"].replace("#", "-"),
                        self.player_dict[x[0]]["Name"],
                        self.player_dict[x[1]]["ID"].replace("#", "-"),
                        self.player_dict[x[1]]["Name"],
                        self.player_dict[x[2]]["ID"].replace("#", "-"),
                        self.player_dict[x[2]]["Name"],
                        self.player_dict[x[3]]["ID"].replace("#", "-"),
                        self.player_dict[x[3]]["Name"],
                        self.player_dict[x[4]]["ID"].replace("#", "-"),
                        self.player_dict[x[4]]["Name"],
                        self.player_dict[x[5]]["ID"].replace("#", "-"),
                        self.player_dict[x[5]]["Name"],
                        self.player_dict[x[6]]["ID"].replace("#", "-"),
                        self.player_dict[x[6]]["Name"],
                        self.player_dict[x[7]]["ID"].replace("#", "-"),
                        self.player_dict[x[7]]["Name"],
                        self.player_dict[x[8]]["ID"].replace("#", "-"),
                        self.player_dict[x[8]]["Name"],
                        salary,
                        round(fpts_p, 2),
                        mins,
                        stddev,
                    )
                    f.write("%s\n" % lineup_str)
        print("Output done.")
        self.print_top_150_lineup_exposures()

        high_exposure_players = self.get_high_exposure_players(10)  # Players with more than 10% exposure

        # Get all pairs and trios from these players
        pairs = self.get_combinations(high_exposure_players, 2)
        trios = self.get_combinations(high_exposure_players, 3)

        # Calculate and print exposure for pairs and trios
        pairs_exposure_df = self.calculate_combination_exposure(pairs, self.num_lineups)
        trios_exposure_df = self.calculate_combination_exposure(trios, self.num_lineups)

        # Save to CSV files
        output_dir = r"C:\Users\samba\OneDrive\Desktop\DFS\NBA\python optimizer\NBA-DFS-Tools-master\output"  # Replace with your output directory path
        pairs_exposure_df.to_csv(os.path.join(output_dir, "pairs_exposure.csv"), index=False)
        trios_exposure_df.to_csv(os.path.join(output_dir, "trios_exposure.csv"), index=False)

        # Print only high exposures
        threshold = 10  # Define your threshold
        print("High Exposure Pairs:\n", pairs_exposure_df[pairs_exposure_df['Exposure (%)'] > threshold])
        print("\nHigh Exposure Trios:\n", trios_exposure_df[trios_exposure_df['Exposure (%)'] > threshold])


    def sort_lineup(self, lineup):
        if self.site == "dk":
            order = ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]
            sorted_lineup = [None] * 8
        else:
            order = ["PG", "PG", "SG", "SG", "SF", "SF", "PF", "PF", "C"]
            sorted_lineup = [None] * 9

        for player in lineup:
            player_key, pos, _ = player
            order_idx = order.index(pos)
            if sorted_lineup[order_idx] is None:
                sorted_lineup[order_idx] = player_key
            else:
                sorted_lineup[order_idx + 1] = player_key
        return sorted_lineup

    def adjust_roster_for_late_swap(self, lineup):
        if self.site == "fd":
            return lineup

        sorted_lineup = list(lineup)

        # A function to swap two players if the conditions are met
        def swap_if_needed(primary_pos, flex_pos):
            primary_player = sorted_lineup[primary_pos]
            flex_player = sorted_lineup[flex_pos]

            # Check if the primary player's game time is later than the flexible player's
            if (
                    self.player_dict[primary_player]["GameTime"]
                    > self.player_dict[flex_player]["GameTime"]
            ):
                primary_positions = self.position_map[primary_pos]
                flex_positions = self.position_map[flex_pos]

                # Check that both players are eligible for the position swaps
                if any(
                        pos in primary_positions
                        for pos in self.player_dict[flex_player]["Position"]
                ) and any(
                    pos in flex_positions
                    for pos in self.player_dict[primary_player]["Position"]
                ):
                    sorted_lineup[primary_pos], sorted_lineup[flex_pos] = (
                        sorted_lineup[flex_pos],
                        sorted_lineup[primary_pos],
                    )

        # Define eligible positions for each spot on the roster
        self.position_map = {
            0: ["PG"],
            1: ["SG"],
            2: ["SF"],
            3: ["PF"],
            4: ["C"],
            5: ["PG", "SG"],
            6: ["SF", "PF"],
            7: ["PG", "SG", "SF", "PF", "C"],
        }

        # Check each primary position against all flexible positions
        for i in range(5):
            for j in range(5, 8):
                swap_if_needed(i, j)

        return sorted_lineup