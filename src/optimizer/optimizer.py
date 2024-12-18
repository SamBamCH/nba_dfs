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
        Ensures players with earlier game times are positioned in restrictive slots when possible.

        :param lineup: List of tuples (player, position) representing the lineup.
        :return: Adjusted lineup.
        """
        if self.site == "fd":
            return lineup  # No late swap needed for FanDuel

        sorted_lineup = list(lineup)  # Copy lineup for sorting

        # Swap players in primary and flex positions based on game time
        def swap_if_needed(primary_pos, flex_pos):
            primary_player, primary_position = sorted_lineup[primary_pos]
            flex_player, flex_position = sorted_lineup[flex_pos]

            # print(f"primary_player.gametime = {primary_player.gametime}, {primary_player.name} vs. flex_player.gametime = {flex_player.gametime}, {flex_player.name}")

            # Only swap if the primary player's game time is later than the flex player's
            if primary_player.gametime > flex_player.gametime:
                primary_positions = self.position_map[primary_pos]
                flex_positions = self.position_map[flex_pos]

                # Check if positions are compatible for swapping
                if (
                    any(pos in primary_positions for pos in flex_player.position) and
                    any(pos in flex_positions for pos in primary_player.position)
                ):
                    # Perform the swap
                    sorted_lineup[primary_pos], sorted_lineup[flex_pos] = (
                        sorted_lineup[flex_pos],
                        sorted_lineup[primary_pos],
                    )

        # Iterate over the lineup positions to apply swaps
        for primary_pos in self.position_map.keys():
            for flex_pos in range(primary_pos + 1, len(sorted_lineup)):
                # Ensure flex_pos exists in position_map
                if flex_pos in self.position_map:
                    swap_if_needed(primary_pos, flex_pos)

        return sorted_lineup




    def run(self):
        """
        Run the optimization process with scaled metrics and penalized exposure.
        :return: Lineups instance containing optimized lineups.
        """
        lineups = Lineups()  # Object to store all generated lineups
        exclusion_constraints = []  # List to store uniqueness constraints

        # Load weights and parameters from config
        weights = self.config.get("weights", {"proj": 1, "own": 0.0, "ceil": 0.0})
        max_exposure_impact = self.config.get("exposure_penalty_max_impact", 0.00)
        fpts_randomness = self.config.get("fpts_randomness_amount", 10) / 100
        ceil_randomness = self.config.get("ceil_randomness_amount", 10) / 100
        own_randomness = self.config.get("own_randomness_amount", 10) / 100

        exposure_penalty_weight = max_exposure_impact / self.num_lineups


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
            fpts_random = {player: np.random.normal(player.fpts, player.stddev * fpts_randomness) for player in self.players}
            ceil_random = {player: np.random.normal(player.ceiling, player.std_boom_pct * ceil_randomness) for player in self.players}
            own_random = {player: np.random.normal(player.ownership, player.std_ownership * own_randomness) for player in self.players}

            # Step 3: Scaling stats to [0, 1]
            max_fpts = max(fpts_random.values(), default=1)
            max_ceil = max(ceil_random.values(), default=1)
            max_own = max(own_random.values(), default=1)

            scaled_fpts = {player: val / max_fpts for player, val in fpts_random.items()}
            scaled_ceil = {player: val / max_ceil for player, val in ceil_random.items()}
            scaled_own = {player: val / max_own for player, val in own_random.items()}


            # Step 5: Set the scaled and penalized objective function
            # Step 5: Set the scaled and penalized objective function
            self.problem.setObjective(
                    lpSum(
                    (
                        weights["proj"] * scaled_fpts[player]
                        + weights["ceil"] * scaled_ceil[player]
                        + weights["own"] * scaled_own[player]
                        - exposure_penalty_weight * self.player_exposure[player]
                    ) * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                )
            )


            # Solve the problem
            try:
                self.problem.solve(plp.GLPK(msg=0))
                self.problem.writeLP(f'problem.lp')
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
                self.player_exposure[player] += 1

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
    

    






