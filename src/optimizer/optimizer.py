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
        Run the optimization process to generate lineups.
        :return: Lineups instance containing optimized lineups.
        """
        # Create a Lineups instance
        lineups = Lineups()
        selected_lineups = []  # Track generated lineups

        # Set constraints using ConstraintManager
        constraint_manager = ConstraintManager(
            self.site, self.problem, self.players, self.lp_variables, self.config
        )
        constraint_manager.add_all_constraints([], self.num_uniques)

        # Loop to generate `num_lineups` lineups
        for i in range(self.num_lineups):
            # Step 1: Generate random projections for all players
            random_projections = {}
            for player in self.players:
                for position in player.position:
                    random_projections[(player, position)] = np.random.normal(
                        player.fpts, player.stddev * self.config["randomness_amount"] / 100
                    )

            # Step 2: Update the objective function
            self.problem.setObjective(
                lpSum(
                    random_projections[(player, position)] * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                )
            )

            # Step 3: Solve the problem
            try:
                self.problem.solve(plp.PULP_CBC_CMD(msg=0))
            except plp.PulpSolverError:
                print(
                    f"Infeasibility reached - only generated {len(lineups)} lineups out of {self.num_lineups}. Continuing."
                )
                break

            # Check for infeasibility
            if plp.LpStatus[self.problem.status] != "Optimal":
                print(
                    f"Infeasibility reached - only generated {len(lineups)} lineups out of {self.num_lineups}. Continuing."
                )
                break

            # Step 4: Extract the lineup from the solved variables
            selected_vars = [
                key for key, var in self.lp_variables.items() if var.varValue == 1
            ]
            lineup = [(player, position) for player, position in selected_vars]

            # Add the lineup to the Lineups object
            lineups.add_lineup(lineup)
            selected_lineups.append(lineup)  # Track this lineup

            # Step 5: Add a uniqueness constraint for this lineup
            player_keys_to_exclude = [
                self.lp_variables[(player, position)] for player, position in lineup
            ]
            self.problem += (
                lpSum(player_keys_to_exclude) <= len(lineup) - self.num_uniques,
                f"Uniqueness_Constraint_{i}"
            )

        self.problem.writeLP("debug_model.lp")
        return lineups

