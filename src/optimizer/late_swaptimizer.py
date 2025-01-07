from pulp import LpProblem, LpMaximize, lpSum, LpVariable, LpBinary
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

                # print(f"locked_player: {locked_player}")

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
        :param fpts_buffer: Multiplier for fpts sum to adjust constraints dynamically.
        :param ownership_buffer: Multiplier for ownership sum to adjust constraints dynamically.
        :return: Optimized lineup.
        """
        # Reset the optimization problem
        self.problem = LpProblem(f"Late_Swap_Optimization_{lineup['Entry ID']}", LpMaximize)

        # Filter players whose games are not locked
        eligible_players = [
            player for player in self.players if not player.is_game_locked()
        ]

        # Add static constraints
        constraint_manager = ConstraintManager(
            self.site, self.problem, self.players, self.lp_variables, self.config
        )
        constraint_manager.add_static_constraints()

        # Apply locked player constraints
        self.apply_locked_constraints(lineup)

        # Optimize once to calculate dynamic constraints
        self.problem.setObjective(
            lpSum(player.fpts * self.lp_variables[(player, position)]
                  for player in eligible_players
                  for position in player.position)
        )
        self.problem.solve(plp.GLPK(msg=0))

        # Calculate fpts and ownership sums from the optimized lineup
        fpts_sum = sum(
            player.fpts for (player, _), var in self.lp_variables.items() if var.varValue == 1
        )
        
        fpts_buffer = self.config.get("fpts_buffer", 0.98)
        max_ownership_sum = self.config.get("max_ownership_sum")
        ceiling_weight = self.config.get("ceiling_weight")
        ownership_weight = self.config.get("ownership_weight")
        randomness_factor = self.config.get("randomness_amount", 10) / 100  # Example: 10% randomness


        # Adjust constraints dynamically
        dynamic_min_fpts = fpts_buffer * fpts_sum
        print(f"min_fpts: {dynamic_min_fpts}, max_ownership_sum: {max_ownership_sum}")
        constraint_manager.add_optional_constraints(dynamic_min_fpts, max_ownership_sum)

        sampled_ceiling_values = {}
        sampled_ownership_values = {}

        # Add randomness to ceiling values
        for player in eligible_players:
            # Example: random normal ~ (mean = player.ceiling, std ~ 1/4 of ceiling * randomness_factor)
            # Tweak the factor as desired to not overshoot too much
            ceiling_stddev = player.boom_pct * 0.25
            ownership_stddev = player.ownership * 0.25

            random_ceiling = np.random.normal(player.boom_pct, ceiling_stddev * randomness_factor)
            random_ownership = np.random.normal(player.ownership, ownership_stddev * randomness_factor)

            # Clip them to ensure no negative ownership, no crazy negative ceiling
            random_ceiling = max(0.0, random_ceiling)
            random_ownership = max(0.0, random_ownership)

            sampled_ceiling_values[player] = random_ceiling
            sampled_ownership_values[player] = random_ownership

        # Scale randomized values
        max_ownership = max(sampled_ownership_values.values(), default=1)  # Avoid division by zero
        scaled_sampled_ownership = {player: value / max_ownership for player, value in sampled_ownership_values.items()}
        max_ceiling = max(sampled_ceiling_values.values(), default=1)
        scaled_sampled_ceiling = {player: value / max_ceiling for player, value in sampled_ceiling_values.items()}

        self.problem.setObjective(
            lpSum(
                (
                    ceiling_weight * scaled_sampled_ceiling[player]
                    - ownership_weight * scaled_sampled_ownership[player]
                ) * self.lp_variables[(player,position)]
                for player in eligible_players
                for position in player.position
            )
        )

        # Solve the optimization problem again with dynamic constraints
        try:
            self.problem.solve(plp.GLPK(msg=0))
        except plp.PulpSolverError:
            print(f"Error optimizing lineup {lineup['Entry ID']}. Skipping...")
            return None

        # Check if the solution is valid
        if plp.LpStatus[self.problem.status] != "Optimal":
            print(f"Optimization failed for lineup {lineup['Entry ID']}.")
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
        to an output CSV file in the specified format.
        :param output_csv_path: Path to save the output CSV file with optimized lineups.
        """
        # Convert the input lineups into a DataFrame for easy manipulation
        lineups_df = pd.DataFrame(self.lineups)
        lineups = Lineups()


        # Loop through each lineup and optimize it
        for index, lineup in lineups_df.iterrows():
            # print(f"Optimizing lineup for entry ID {lineup['Entry ID']}...")

            # Convert the current row to a dictionary
            lineup_dict = lineup.to_dict()

            # Check if all players in the lineup are locked based on the '_is_locked' flags
            locked_players = [
                lineup_dict.get(f"{position}_is_locked", False) 
                for position in ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]
            ]
            
            # If all players are locked, skip this lineup and do nothing else
            if all(locked_players):
                print(f"All players are locked for lineup {lineup['Entry ID']}. Skipping optimization.")
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

        # Define the desired output columns
        output_columns = [
            "Entry ID", "Contest Name", "Contest ID", "Entry Fee",
            "PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"
        ]

        # Filter the DataFrame to include only the desired columns
        if not set(output_columns).issubset(lineups_df.columns):
            missing_columns = set(output_columns) - set(lineups_df.columns)
            raise KeyError(f"Missing required columns in DataFrame: {missing_columns}")

        formatted_df = lineups_df[output_columns]
        
        # Save the updated lineups to a CSV file
        formatted_df.to_csv(output_csv_path, index=False)
        print(f"Optimized lineups have been written to {output_csv_path}")
        return lineups




