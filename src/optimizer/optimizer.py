from pulp import LpProblem, LpMaximize, LpVariable, lpSum
from optimizer.constraints import ConstraintManager
import numpy as np


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
        self.lp_variables = {
            player: {
                pos: LpVariable(f"{player.name}_{pos}_{player.team}", cat="Binary")
                for pos in player.position
            }
            for player in players
        }
        self.lineups = []

    def run(self):
        """
        Run the optimization process to generate lineups.
        :return: List of optimized lineups.
        """
        for _ in range(self.num_lineups):
            # Reset problem for each lineup
            self.problem = LpProblem("DFS_Optimization", LpMaximize)

            # Add constraints and objective
            constraint_manager = ConstraintManager(
                self.site, self.problem, self.players, self.lp_variables, self.config
            )
            constraint_manager.add_all_constraints(
                selected_lineups=self.lineups, num_uniques=self.num_uniques
            )
            self._set_objective()

            # Solve the optimization problem
            self.problem.solve()

            # Extract selected lineup
            lineup = self._extract_lineup()
            if lineup:
                self.lineups.append(lineup)
            else:
                break  # Stop if no valid lineup is found

        return self.lineups

    def _set_objective(self):
        """
        Set the objective function: Maximize fantasy points with randomness.
        """
        randomness = self.config.get("randomness", 0)
        if randomness:
            self.problem += lpSum(
                np.random.normal(player.fpts, player.stddev * randomness / 100)
                * self.lp_variables[player][pos]
                for player in self.players
                for pos in player.position
            ), "Maximize FPTS with Randomness"
        else:
            self.problem += lpSum(
                player.fpts * self.lp_variables[player][pos]
                for player in self.players
                for pos in player.position
            ), "Maximize FPTS"

    def _extract_lineup(self):
        """
        Extract a lineup from the solved LP problem.
        :return: List of Player objects in the lineup.
        """
        lineup = []
        for player, positions in self.lp_variables.items():
            for pos, var in positions.items():
                if var.varValue == 1:
                    lineup.append(player)
                    break  # Only include the player once
        return lineup if lineup else None
