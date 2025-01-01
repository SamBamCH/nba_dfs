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
        Run the optimization process in two stages:
        1. Extract the baseline fpts and ownership from the first lineup.
        2. Use these baseline values to set constraints and maximize ceiling with added randomness.
        :return: Lineups instance containing optimized lineups.
        """
        lineups = Lineups()  # Object to store all generated lineups
        exclusion_constraints = []  # List to store uniqueness constraints
        
        min_fpts = None
        max_ownership = None
        randomness_factor = self.config.get("randomness_amount", 10) / 100  # Example: 10% randomness

        # Stage 1: Generate the initial lineup to determine baseline values
        self.problem = LpProblem("Stage1_NBA_DFS_Optimization", LpMaximize)
        print('STAGE 1 OF OPTIMIZATION:')

        constraint_manager = ConstraintManager(
            self.site, self.problem, self.players, self.lp_variables, self.config
        )
        constraint_manager.add_static_constraints()
        print(f'max_ownership = {max_ownership}, min_fpts = {min_fpts}')


        # Objective: Maximize fpts for the initial lineup
        self.problem.setObjective(
            lpSum(
                player.fpts * self.lp_variables[(player, position)]
                for player in self.players
                for position in player.position
            )
        )

        # Solve the initial problem
        try:
            self.problem.solve(plp.GLPK(msg=0))
        except plp.PulpSolverError:
            print("Infeasibility during Stage 1 optimization.")
            return lineups

        if plp.LpStatus[self.problem.status] != "Optimal":
            print("No optimal solution found during Stage 1 optimization.")
            return lineups

        # Extract the first lineup and calculate baseline values
        final_vars = [
            key for key, var in self.lp_variables.items() if var.varValue == 1
        ]
        final_lineup = [(player, position) for player, position in final_vars]

        baseline_fpts = None
        max_ownership = None
        baseline_fpts = sum(player.fpts for player, _ in final_lineup)
        fpts_buffer = self.config.get("fpts_buffer", 0.98)
        min_fpts = fpts_buffer * baseline_fpts
        
        print(f"top projected lineup: {baseline_fpts}, min_fpts: {min_fpts}")

        self.problem = LpProblem("stage2_nba_dfs_optimization", LpMaximize)
        print('STAGE 2 OF OPTIMIZATION:')
        constraint_manager = ConstraintManager(
            self.site, self.problem, self.players, self.lp_variables, self.config
        )
        constraint_manager.add_static_constraints()
        print(f'max_ownership = {max_ownership}, min_fpts = {min_fpts}')
        constraint_manager.add_optional_constraints(
            max_ownership,
            min_fpts  # Allow a small buffer for flexibility

        )
        self.problem.setObjective(
            lpSum(
                player.ownership * self.lp_variables[(player, position)]
                for player in self.players
                for position in player.position
            )
        )

        try: 
            self.problem.solve(plp.GLPK(msg=0))
        except plp.PulpSolverError:
            print("infeasibility during stage 2 optimization")
            return lineups
        
        if plp.LpStatus[self.problem.status] != "Optimal":
            print("no optimal solution found during stage 2 optimization.")
            return lineups
        
        final_vars = [
            key for key, var in self.lp_variables.items() if var.varValue == 1
        ]
        final_lineup = [(player, position) for player, position in final_vars]
        ownership_buffer = self.config.get("ownership_buffer")
        baseline_ownership = sum(player.ownership for player, _ in final_lineup)
        max_ownership = ownership_buffer * baseline_ownership

        print(f'top owned lineup: {baseline_ownership}, ownership limit: {max_ownership}, ownership_buffer: {ownership_buffer}')


        # Stage 3: Optimize subsequent lineups with added randomness
        for i in range(self.num_lineups):
            if i % 10 == 0: 
                print(i)
            self.problem = LpProblem(f"Stage2_NBA_DFS_Optimization_{i}", LpMaximize)

            # Reinitialize constraints for the new problem
            constraint_manager = ConstraintManager(
                self.site, self.problem, self.players, self.lp_variables, self.config
            )
            constraint_manager.add_static_constraints()
            constraint_manager.add_optional_constraints(max_ownership, min_fpts)

            # Reapply exclusion constraints for uniqueness
            for constraint in exclusion_constraints:
                self.problem += constraint

            # Add randomness to ceiling values
            random_projections = {
                player: np.random.normal(player.fpts, player.stddev * randomness_factor)
                for player in self.players
            }

            # Scale randomized ceiling values
            max_projections = max(random_projections.values(), default=1)  # Avoid division by zero
            scaled_random_projections = {player: value / max_projections for player, value in random_projections.items()}

            # Objective: Maximize randomized ceiling
            self.problem.setObjective(
                lpSum(
                    scaled_random_projections[player] * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                )
            )

            # Solve the problem
            try:
                self.problem.solve(plp.GLPK(msg=0))
            except plp.PulpSolverError:
                print(f"Infeasibility during Stage 2 optimization for lineup {i}.")
                break

            if plp.LpStatus[self.problem.status] != "Optimal":
                print(f"No optimal solution for lineup {i} in Stage 2.")
                break

            # Extract the lineup and save it
            final_vars = [
                key for key, var in self.lp_variables.items() if var.varValue == 1
            ]
            final_lineup = [(player, position) for player, position in final_vars]
            self.adjust_roster_for_late_swap(final_lineup)
            lineups.add_lineup(final_lineup)

            # Add exclusion constraint to prevent exact duplicate lineups
            player_ids = [player.id for player, _ in final_lineup]
            player_keys_to_exclude = [
                (p, pos) for p in self.players if p.id in player_ids for pos in p.position
            ]
            exclusion_constraint = lpSum(
                self.lp_variables[(player, pos)] for player, pos in player_keys_to_exclude
            ) <= len(final_vars) - self.num_uniques
            exclusion_constraints.append(exclusion_constraint)

        return lineups


    

    






