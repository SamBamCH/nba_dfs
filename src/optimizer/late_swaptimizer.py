from pulp import LpProblem, LpMaximize, lpSum
from optimizer.constraints import ConstraintManager
import numpy as np
from lineups.lineups import Lineups
import pulp as plp
import re
import pandas as pd


class LateSwaptimizer:
    def __init__(self, site, players, config, lineups):
        self.site = site
        self.players = players
        self.config = config
        self.lineups = lineups  # Dictionary of input lineups
        self.problem = None
        self.lp_variables = {}
        self.position_map = {i: ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"] for i in range(len(players))}

        # Create LP variables for each player and position
        for player in players:
            for position in player.position:
                var_name = f"{player.name}_{position}_{player.id}"
                self.lp_variables[(player, position)] = plp.LpVariable(
                    name=var_name, cat=plp.LpBinary
                )

    def apply_locked_constraints(self, lineup):
        """
        Add constraints for locked players in the lineup.
        :param lineup: Dictionary representing a single lineup.
        """
        for position, locked_key in [
            ("PG", "PG_is_locked"),
            ("SG", "SG_is_locked"),
            ("SF", "SF_is_locked"),
            ("PF", "PF_is_locked"),
            ("C", "C_is_locked"),
            ("G", "G_is_locked"),
            ("F", "F_is_locked"),
            ("UTIL", "UTIL_is_locked"),
        ]:
            if lineup[locked_key]:  # If the player is locked
                locked_player_id = re.search(r"\((\d+)\)", lineup[position]).group(1)
                locked_player = next((p for p in self.players if p.id == locked_player_id), None)

                if locked_player:
                    # Ensure this player is selected for the specified position
                    self.problem += (
                        self.lp_variables[(locked_player, position)] == 1,
                        f"{position}_locked_constraint_{locked_player_id}",
                    )
                else:
                    print(f"Warning: Locked player ID {locked_player_id} not found.")

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

    def optimize_single_lineup(self, lineup):
        """
        Optimize a single lineup with the locked players treated as constraints.
        :param lineup: Dictionary representing a single lineup.
        :return: Optimized lineup.
        """
        # Reset the optimization problem
        self.problem = LpProblem(f"Late_Swap_Optimization_{lineup['entry_id']}", LpMaximize)

        # Add static constraints
        constraint_manager = ConstraintManager(
            self.site, self.problem, self.players, self.lp_variables, self.config
        )
        constraint_manager.add_static_constraints()

        lambda_weight = self.config.get("ownership_lambda", 0)


        # Apply locked player constraints
        self.apply_locked_constraints(lineup)

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

        # Define the objective function
        self.problem.setObjective(
                lpSum(
                    (
                        scaled_projections[(player, position)] - 
                        (lambda_weight * scaled_ownership[player]) + 
                        scaled_boom[player]
                    ) * self.lp_variables[(player, position)]
                    for player in self.players
                    for position in player.position
                )
            )
        self.problem.writeLP("problem.lp")
        # Solve the optimization problem
        try:
            self.problem.solve(plp.GLPK(msg=0))
        except plp.PulpSolverError:
            print(f"Error optimizing lineup {lineup['entry_id']}. Skipping...")
            return None

        # Check if the solution is valid
        if plp.LpStatus[self.problem.status] != "Optimal":
            print(f"Optimization failed for lineup {lineup['entry_id']}.")
            return None

        # Extract the optimized lineup
        optimized_lineup = [
            (player, position)
            for (player, position), var in self.lp_variables.items()
            if var.varValue == 1
        ]
        return optimized_lineup

        

    def run(self, output_csv_path):
        """
        Loop through the input lineups, optimize each one, and write the optimized lineup 
        to an output CSV file in the same format as the input.
        :param output_csv_path: Path to save the output CSV file with optimized lineups.
        """
        # Convert the input lineups into a DataFrame for easy manipulation
        lineups_df = pd.DataFrame(self.lineups)
        lineups = Lineups()

        # Loop through each lineup and optimize it
        for index, lineup in lineups_df.iterrows():
            print(f"Optimizing lineup for entry ID {lineup['entry_id']}...")

            # Convert the current row to a dictionary
            lineup_dict = lineup.to_dict()

            # Check if all players in the lineup are locked based on the 'is_locked' flags
            locked_players = [
                lineup_dict.get(f"{position}_is_locked", False) 
                for position in ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]
            ]
            
            # If all players are locked, skip this lineup and do nothing else
            if all(locked_players):
                print(f"All players are locked for lineup {lineup['entry_id']}. Skipping optimization.")
                continue  # Skip this lineup and move to the next one

            # Optimize the lineup with locked player constraints
            optimized_lineup = self.optimize_single_lineup(lineup_dict)
            optimized_lineups = self.adjust_roster_for_late_swap(optimized_lineup)
            lineups.add_lineup(optimized_lineups)

            if optimized_lineup:
                # Convert the optimized lineup into a readable format
                optimized_lineup_dict = {
                    position: f"{player.name} ({player.id})"
                    for player, position in optimized_lineup
                }

                # Update the DataFrame with optimized values
                for position in ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]:
                    lineups_df.at[index, position] = optimized_lineup_dict.get(position, lineup[position])

        # Save the updated lineups to a CSV file
        lineups_df.to_csv(output_csv_path, index=False)
        print(f"Optimized lineups have been written to {output_csv_path}")
        return lineups



