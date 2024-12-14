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

        self.position_map = {i: ["G", "F", "C", "UTIL"] for i in range(len(players))}

        # Create LP variables for each player and position
        for player in players:
            for position in player.position:
                var_name = f"{player.name}_{position}_{player.id}"
                self.lp_variables[(player, position)] = plp.LpVariable(
                    name=var_name, cat=plp.LpBinary
                )

    def adjust_roster_for_late_swap(self, lineup):
        """
        Adjusts a roster to optimize for late swap.
        Ensures players with later game times are positioned in flex spots when possible.

        :param lineup: List of tuples (player, position) representing the lineup.
        :return: Adjusted lineup.
        """
        if self.site == "fd":
            return lineup  # No late swap needed for FanDuel

        sorted_lineup = list(lineup)

        # Swap players in primary and flex positions based on game time
        def swap_if_needed(primary_pos, flex_pos):
            primary_player, primary_position = sorted_lineup[primary_pos]
            flex_player, flex_position = sorted_lineup[flex_pos]

            # Check if the primary player's game time is later than the flex player's
            if (
                primary_player.gametime > flex_player.gametime
            ):
                primary_positions = self.position_map[primary_pos]
                flex_positions = self.position_map[flex_pos]

                # Ensure both players are eligible for position swaps
                if any(
                    pos in primary_positions
                    for pos in flex_player.position
                ) and any(
                    pos in flex_positions
                    for pos in primary_player.position
                ):
                    # Perform the swap
                    sorted_lineup[primary_pos], sorted_lineup[flex_pos] = (
                        sorted_lineup[flex_pos],
                        sorted_lineup[primary_pos],
                    )

        # Iterate over positions to check and apply swaps
        for primary_pos in range(len(sorted_lineup)):
            for flex_pos in range(primary_pos + 1, len(sorted_lineup)):
                swap_if_needed(primary_pos, flex_pos)

        return sorted_lineup


    def run(self):
        """
        Run the optimization process with scaled metrics and penalized exposure.
        :return: Lineups instance containing optimized lineups.
        """
        lineups = Lineups()  # Object to store all generated lineups
        exclusion_constraints = []  # List to store uniqueness constraints

        # Weights for each component in the objective function
        lambda_weight = self.config.get("ownership_lambda", 0)
        exposure_penalty_weight = self.config.get("exposure_penalty_weight", 0.01)  # Weight for exposure penalty

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
            max_fpts = max(random_projections.values(), default=1)  # Avoid division by zero
            max_boom = max(random_boom.values(), default=1)
            max_ownership = max(random_ownership.values(), default=1)
            max_exposure = max(max(self.player_exposure.values(), default=0), 1)


            # Step 4: Scale each variable to range [0, 1]
            scaled_projections = {
                key: value / max_fpts for key, value in random_projections.items()
            }

            scaled_boom = {
                player: value / max_boom for player, value in random_boom.items()
            }

            scaled_ownership = {
                player: value / max_ownership for player, value in random_ownership.items()
            }

            scaled_exposure = {
                player: self.player_exposure[player] / max_exposure for player in self.players
            }

            # Step 5: Set the scaled and penalized objective function
            self.problem.setObjective(
                lpSum(
                    (
                        scaled_projections[(player, position)] - 
                        (lambda_weight * scaled_ownership[player]) + 
                        scaled_boom[player] - 
                        (exposure_penalty_weight * scaled_exposure[player])
                    ) * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                )
            )

            # Solve the problem
            try:
                self.problem.solve(plp.GLPK(msg=0))
            except plp.PulpSolverError:
                print(f"Infeasibility reached during optimization. Only {len(lineups.lineups)} lineups generated.")
                break

            if plp.LpStatus[self.problem.status] != "Optimal":
                print(f"Infeasibility reached during optimization. Only {len(lineups.lineups)} lineups generated.")
                break

            # Step 6: Extract and save the final lineup
            final_vars = [
                key for key, var in self.lp_variables.items() if var.varValue == 1
            ]
            final_lineup = [(player, position) for player, position in final_vars]
            final_lineup = self.adjust_roster_for_late_swap(final_lineup)
            lineups.add_lineup(final_lineup)

            # Step 7: Update player exposure
            for player, position in final_vars:
                self.player_exposure[player] += 2 * player.variance_score

            # Step 8: Add exclusion constraint for uniqueness
            player_ids = [player.id for player, _ in final_vars]
            player_keys_to_exclude = [
                (p, pos) for p in self.players if p.id in player_ids for pos in p.position
            ]
            exclusion_constraint = lpSum(
                self.lp_variables[(player, pos)] for player, pos in player_keys_to_exclude
            ) <= len(final_vars) - self.num_uniques
            exclusion_constraints.append(exclusion_constraint)

        return lineups
    

    






