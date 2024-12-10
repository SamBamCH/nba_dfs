from pulp import LpProblem, LpMaximize, LpVariable, lpSum
from optimizer.constraints import ConstraintManager
import numpy as np
import pulp as plp
from lineups.lineups import Lineups


class Optimizer:
    def __init__(self, site, players, num_lineups, num_uniques, config):
        """
        Initialize the Optimizer.
        :param site: Platform (e.g., 'dk' or 'fd').
        :param players: List of Player objects.
        :param num_lineups: Number of lineups to generate.
        :param num_uniques: Minimum unique players between lineups.
        :param config: Configuration dictionary.
        """
        self.site = site
        self.players = players
        self.num_lineups = num_lineups
        self.num_uniques = num_uniques
        self.config = config
        self.problem = LpProblem("DFS_Optimization", LpMaximize)
        self.lp_variables = {}

        # Create LP variables for each player and position
        for player in players:
            if not player.id:
                print(f"Player {player.name} does not have an ID. Skipping.")
                continue

            for position in player.position:  # Assuming `player.position` is a list of positions
                variable_name = f"{player.name}_{position}_{player.id}"
                self.lp_variables[(player, position)] = plp.LpVariable(
                    name=variable_name, cat=plp.LpBinary
                )

    def run(self):
        """
        Iteratively build the lineup by solving for different objectives at each step.
        :return: Lineups instance containing optimized lineups.
        """
        # Create a Lineups instance
        lineups = Lineups()
        selected_lineups = []  # Store final lineups

        for i in range(self.num_lineups):
            self.problem = LpProblem(f"Lineup_{i}", LpMaximize)
            locked_players = []

            # Initialize ConstraintManager
            constraint_manager = ConstraintManager(
                self.site, self.problem, self.players, self.lp_variables, self.config
            )
            constraint_manager.add_all_constraints(locked_players, self.num_uniques)

            # Stage 1: Select 4 value players
            self.problem.setObjective(
                lpSum(
                    (player.fpts / player.salary) * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                )
            )
            self.problem.solve(plp.PULP_CBC_CMD(msg=0))
            if self.problem.status != 1:
                print(f"Failed to solve for value players in iteration {i}.")
                continue

            # Lock top 4 value players
            value_players = [
                (player, position)
                for (player, position), var in self.lp_variables.items()
                if var.varValue == 1
            ][:4]
            for player, position in value_players:
                self.problem += self.lp_variables[(player, position)] == 1
                locked_players.append((player, position))

            # Stage 2: Add the highest median projection player under an ownership threshold
            self.problem.setObjective(
                lpSum(
                    player.fpts * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                    if player.ownership < 0.1  # Ownership threshold
                )
            )
            self.problem.solve(plp.PULP_CBC_CMD(msg=0))
            if self.problem.status != 1:
                print(f"Failed to solve for low-owned player in iteration {i}.")
                continue

            low_owned_player = [
                (player, position)
                for (player, position), var in self.lp_variables.items()
                if var.varValue == 1
            ][:1]  # Only one low-owned player
            for player, position in low_owned_player:
                self.problem += self.lp_variables[(player, position)] == 1
                locked_players.append((player, position))

            # Stage 3: Fill the lineup with ceiling players
            self.problem.setObjective(
                lpSum(
                    player.ceiling * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                )
            )
            self.problem.solve(plp.PULP_CBC_CMD(msg=0))
            if self.problem.status != 1:
                print(f"Failed to solve for ceiling players in iteration {i}.")
                continue

            # Extract the final lineup
            final_lineup = [
                (player, position)
                for (player, position), var in self.lp_variables.items()
                if var.varValue == 1
            ]
            lineups.add_lineup(final_lineup)
            selected_lineups.append(final_lineup)

            # Add uniqueness constraint
            player_keys_to_exclude = [
                self.lp_variables[(player, position)] for player, position in final_lineup
            ]
            self.problem += (
                lpSum(player_keys_to_exclude) <= len(final_lineup) - self.num_uniques,
                f"Uniqueness_Constraint_{i}"
            )

        return lineups

