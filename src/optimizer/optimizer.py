from pulp import LpProblem, LpMaximize, lpSum
from optimizer.constraints import ConstraintManager
import numpy as np
from lineups.lineups import Lineups
import pulp as plp


class Optimizer:
    def __init__(self, site, players, num_lineups, num_uniques, config):
        self.site = site
        self.players = players
        self.num_lineups = num_lineups
        self.num_uniques = num_uniques
        self.config = config
        self.problem = LpProblem("NBA_DFS_Optimization", LpMaximize)
        self.lp_variables = {}

        # Create LP variables for each player and position
        for player in players:
            for position in player.position:
                var_name = f"{player.name}_{position}_{player.id}"
                self.lp_variables[(player, position)] = plp.LpVariable(
                    name=var_name, cat=plp.LpBinary
                )

    def run(self):
        lineups = Lineups()
        selected_lineups = []  # Keep track of generated lineups

        # Initialize constraints
        constraint_manager = ConstraintManager(
            self.site, self.problem, self.players, self.lp_variables, self.config
        )
        constraint_manager.add_static_constraints()  # Add static constraints to the optimization problem

        for i in range(self.num_lineups):
            # Step 1: Generate random projections
            random_projections = {
                (player, position): np.random.normal(
                    player.fpts, player.stddev * self.config["randomness_amount"] / 100
                )
                for player in self.players
                for position in player.position
            }

            # Step 2: Update objective function
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
                print(f"Infeasibility reached. Only {len(lineups)} lineups generated.")
                break

            if plp.LpStatus[self.problem.status] != "Optimal":
                print(f"Infeasibility reached. Only {len(lineups)} lineups generated.")
                break

            # Step 4: Extract and save the lineup
            selected_vars = [
                key for key, var in self.lp_variables.items() if var.varValue == 1
            ]
            lineup = [(player, position) for player, position in selected_vars]
            lineups.add_lineup(lineup)
            selected_lineups.append(lineup)

            # Step 5: Ensure this lineup isn't picked again
            player_ids = [player.id for player, _ in selected_vars]
            player_keys_to_exclude = [
                (p, pos) for p in self.players if p.id in player_ids for pos in p.position
            ]

            # Add exclusion constraint
            self.problem += (
                plp.lpSum(self.lp_variables[(player, pos)] for player, pos in player_keys_to_exclude)
                <= len(selected_vars) - self.num_uniques,
                f"Exclude_Lineup_{i}",
            )

        return lineups