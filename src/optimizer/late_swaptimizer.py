from pulp import LpProblem, LpMaximize, lpSum
from optimizer.constraints import ConstraintManager
import numpy as np
from lineups.lineups import Lineups
import pulp as plp
import re


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

        # Apply locked player constraints
        self.apply_locked_constraints(lineup)

        # Define the objective function
        self.problem.setObjective(
            lpSum(
                player.fpts * self.lp_variables[(player, position)]
                for player in self.players
                for position in player.position
            )
        )

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

    def run(self):
        """
        Loop through the input lineups and optimize each one.
        :return: Lineups object containing all optimized lineups.
        """
        optimized_lineups = Lineups()

        for lineup in self.lineups:
            print(f"Optimizing lineup for entry ID {lineup['entry_id']}...")

            # Optimize the lineup with locked player constraints
            optimized_lineup = self.optimize_single_lineup(lineup)

            if optimized_lineup:
                optimized_lineups.add_lineup(optimized_lineup)

        return optimized_lineups
