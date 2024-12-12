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
        self.player_exposure = {player: 0 for player in players}  # Initialize exposure tracker

        # Create LP variables for each player and position
        for player in players:
            for position in player.position:
                var_name = f"{player.name}_{position}_{player.id}"
                self.lp_variables[(player, position)] = plp.LpVariable(
                    name=var_name, cat=plp.LpBinary
                )

    def run(self):
        """
        Run the optimization process with scaled metrics and penalized exposure.
        :return: Lineups instance containing optimized lineups.
        """
        Lineups = Lineups()  # Object to store all generated lineups
        exclusion_constraints = []  # List to store uniqueness constraints

        # Weights for each component in the objective function
        ownership_weight = self.config.get("ownership_weight", 0.1)  # Relative to fpts
        lambda_weight = self.config.get("ownership_lambda", 0)
        exposure_penalty_weight = self.config.get("exposure_penalty_weight", 0.1)  # Weight for exposure penalty

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

            # Step 2: Generate random samples for `fpts`, `boom`, and `ownership`
            random_projections = {
                (player, position): np.random.normal(
                    player.fpts, player.stddev * self.config["randomness_amount"] / 100
                )
                for player in self.players
                for position in player.position
            }

            random_boom = {
                player: np.random.normal(player.ceiling, player.std_boom_pct * self.config["randomness_amount"] / 100)
                for player in self.players
            }

            random_ownership = {
                player: np.random.normal(player.ownership, player.std_ownership * self.config["randomness_amount"] / 100)
                for player in self.players
            }

            # Step 3: Calculate global max for scaling based on random samples
            max_fpts = max(random_projections.values())
            max_boom = max(random_boom.values())
            max_ownership = max(random_ownership.values())

            # Step 4: Set the scaled and penalized objective function
            self.problem.setObjective(
                lpSum(
                    (
                        random_projections[(player, position)] - 
                        (2 * lambda_weight * random_ownership[player]) + 
                        random_boom[player] - 
                        (exposure_penalty_weight * self.player_exposure[player])
                    ) * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                )
            )

            # Solve the problem
            try:
                self.problem.solve(plp.GLPK(msg=0))
            except plp.PulpSolverError:
                print(f"Infeasibility reached during optimization. Only {len(Lineups.lineups)} lineups generated.")
                break

            if plp.LpStatus[self.problem.status] != "Optimal":
                print(f"Infeasibility reached during optimization. Only {len(Lineups.lineups)} lineups generated.")
                break

            # Step 5: Extract and save the final lineup
            final_vars = [
                key for key, var in self.lp_variables.items() if var.varValue == 1
            ]
            final_lineup = [(player, position) for player, position in final_vars]
            Lineups.add_lineup(final_lineup)

            # Step 6: Update player exposure
            for player, position in final_vars:
                self.player_exposure[player] += 1

            # Step 7: Add exclusion constraint for uniqueness
            player_ids = [player.id for player, _ in final_vars]
            player_keys_to_exclude = [
                (p, pos) for p in self.players if p.id in player_ids for pos in p.position
            ]
            exclusion_constraint = lpSum(
                self.lp_variables[(player, pos)] for player, pos in player_keys_to_exclude
            ) <= len(final_vars) - self.num_uniques
            exclusion_constraints.append(exclusion_constraint)

        return Lineups







