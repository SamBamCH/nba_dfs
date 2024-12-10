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
        lineups = Lineups()  # Object to store all generated lineups
        exclusion_constraints = []  # List to store uniqueness constraints

        for i in range(self.num_lineups):
            # Step 1: Reset the optimization problem
            self.problem = LpProblem(f"NBA_DFS_Optimization_{i}", LpMaximize)

            # Reinitialize constraints for the new problem
            constraint_manager = ConstraintManager(
                self.site, self.problem, self.players, self.lp_variables, self.config
            )
            constraint_manager.add_static_constraints()  # Add static constraints

            # Reapply all exclusion constraints from previous iterations
            for constraint in exclusion_constraints:
                self.problem += constraint

            # Step 2: Generate new random `fpts` values for all players
            random_projections = {
                (player, position): np.random.normal(
                    player.fpts, player.stddev * self.config["randomness_amount"] / 100
                )
                for player in self.players
                for position in player.position
            }

            # Step 3: Phase 1 - Select 4 core players maximizing fpts/salary
            self.problem.setObjective(
                lpSum(
                    (random_projections[(player, position)] / player.salary) * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                )
            )

            # Solve Phase 1
            try:
                self.problem.solve(plp.GLPK(msg=0))
            except plp.PulpSolverError:
                print(f"Infeasibility reached during Phase 1. Only {len(lineups.lineups)} lineups generated.")
                break

            if plp.LpStatus[self.problem.status] != "Optimal":
                print(f"Infeasibility reached during Phase 1. Only {len(lineups.lineups)} lineups generated.")
                break

            # Extract the top 4 core players
            core_players = [
                key for key, var in self.lp_variables.items() if var.varValue == 1
            ][:4]

            # Dynamically add a constraint to lock these core players for the current lineup
            core_player_constraint = lpSum(
                self.lp_variables[(player, position)] for player, position in core_players
            ) == 4
            self.problem += core_player_constraint

            # Step 4: Phase 2 - Add the player with the highest ceiling
            remaining_players = [player for player in self.players if player not in [cp[0] for cp in core_players]]
            high_ceiling_player = max(remaining_players, key=lambda p: p.ceiling)
            high_ceiling_constraint = lpSum(
                self.lp_variables[(high_ceiling_player, position)] for position in high_ceiling_player.position
            ) == 1
            self.problem += high_ceiling_constraint

            # Step 5: Phase 3 - Fill remaining slots maximizing fpts
            self.problem.setObjective(
                lpSum(random_projections[(player, position)] * self.lp_variables[(player, position)]
                    for player in self.players for position in player.position)
            )

            # Solve Phase 3
            try:
                self.problem.solve(plp.GLPK(msg=0))
            except plp.PulpSolverError:
                print(f"Infeasibility reached during Phase 3. Only {len(lineups.lineups)} lineups generated.")
                break

            if plp.LpStatus[self.problem.status] != "Optimal":
                print(f"Infeasibility reached during Phase 3. Only {len(lineups.lineups)} lineups generated.")
                break

            # Step 6: Extract and save the final lineup
            final_vars = [
                key for key, var in self.lp_variables.items() if var.varValue == 1
            ]
            final_lineup = [(player, position) for player, position in final_vars]
            lineups.add_lineup(final_lineup)

            # Step 7: Add exclusion constraint for uniqueness
            player_ids = [player.id for player, _ in final_vars]
            player_keys_to_exclude = [
                (p, pos) for p in self.players if p.id in player_ids for pos in p.position
            ]
            exclusion_constraint = lpSum(
                self.lp_variables[(player, pos)] for player, pos in player_keys_to_exclude
            ) <= len(final_vars) - self.num_uniques
            exclusion_constraints.append(exclusion_constraint)

        return lineups




