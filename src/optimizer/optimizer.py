from pulp import LpProblem, LpMaximize, lpSum, LpMinimize
import matplotlib.pyplot as plt
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
        self.min_fpts = 0

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
    
    def explore_fpts_ownership_tradeoff(self, 
                                    min_ratio=0.90, 
                                    max_ratio=1.0, 
                                    steps=5):
        """
        1. We define a range of fpts_min values from `min_ratio * baseline_fpts` 
        to `max_ratio * baseline_fpts`.
        2. For each fpts_min, we solve two problems:
            (a) Minimize sum of ownership
            (b) Maximize sum of ownership
        3. We record (fpts_min, min_ownership, max_ownership).
        4. Plot and compute derivative to find the 'best' fpts_min by slope.

        :param min_ratio: lower fraction of baseline_fpts to begin scanning.
        :param max_ratio: upper fraction of baseline_fpts.
        :param steps: number of increments between min_ratio and max_ratio.
        """
        # -- 1) First, find the baseline_fpts from a 'pure max fpts' solve
        # This is basically what you did in your Stage 1 approach:
        # Solve for the lineup that maximizes FPTS with no min_fpts constraint, 
        # then measure the total FPTS as baseline_fpts.

        stage1_problem = LpProblem("BaselineMaxFPTS", LpMaximize)
        constraint_manager = ConstraintManager(
            self.site, stage1_problem, self.players, self.lp_variables, self.config
        )
        constraint_manager.add_static_constraints()

        # Objective: Maximize total fantasy points
        stage1_problem.setObjective(
            lpSum(
                player.fpts * self.lp_variables[(player, position)]
                for player in self.players
                for position in player.position
            )
        )

        # Solve
        try:
            stage1_problem.solve(plp.GLPK(msg=0))
        except plp.PulpSolverError:
            print("Infeasibility during baseline max-FPTS.")
            return

        if plp.LpStatus[stage1_problem.status] != "Optimal":
            print("No optimal solution found for baseline max-FPTS.")
            return

        # Extract baseline_fpts
        final_vars = [k for k, v in self.lp_variables.items() if v.varValue == 1]
        final_lineup = [(player, pos) for (player, pos) in final_vars]
        baseline_fpts = sum(player.fpts for player, _ in final_lineup)
        print(f"Baseline FPTS found: {baseline_fpts}")

        # We'll store results here
        fpts_min_list = []
        min_ownership_list = []
        max_ownership_list = []

        # -- 2) Loop over a range of min_fpts thresholds
        fpts_values = np.linspace(min_ratio * baseline_fpts, 
                                max_ratio * baseline_fpts, 
                                steps)

        for fpts_min in fpts_values:
            # a) Minimize sum of ownership subject to FPTS >= fpts_min
            min_ownership = self._run_fpts_owned_optimization(
                fpts_min=fpts_min, maximize=False
            )

            fpts_min_list.append(fpts_min)
            min_ownership_list.append(min_ownership)

        # -- 4) Identify best fpts_min by derivative
        # For a rough approach, we'll compute the derivative of min_ownership vs. fpts_min 
        # (which is a discrete approximation). The "best" might be where slope is largest 
        # (or largest negative slope if you're looking at how quickly ownership jumps).  
        # We'll just do it on the min_ownership curve as an example:
        ownership_array = np.array(min_ownership_list)
        fpts_array = np.array(fpts_min_list)

        # numerical derivative = d(ownership)/d(fpts)
        # We want the point where the derivative changes significantly or is minimal, etc.
        # It's up to your logic how you interpret it. 
        # For demonstration, let's pick the point with the biggest negative slope 
        # (the "steepest drop in ownership for a small increment in FPTS_min").
        deriv = np.gradient(ownership_array, fpts_array)  # approximate derivative
        best_idx = np.argmax(deriv)  # or np.argmax(...) depending on your logic
        best_fpts_min = fpts_array[best_idx]

        print("Derivative array:", deriv)
        print(f"Chosen fpts_min based on derivative is {best_fpts_min:.2f}")

        self.min_fpts = best_fpts_min

        # -- 3) Plot the min/max ownership vs. fpts_min on primary y-axis
        fig, ax1 = plt.subplots(figsize=(8, 5))

        color1 = 'tab:blue'
        ax1.set_xlabel('FPTS Minimum Constraint')
        ax1.set_ylabel('Ownership (Sum)', color=color1)
        line1 = ax1.plot(fpts_min_list, min_ownership_list, 
                        marker='o', color=color1, label='Min Ownership')
        ax1.tick_params(axis='y', labelcolor=color1)

        # -- Create a second y-axis for the derivative
        ax2 = ax1.twinx()
        color2 = 'tab:red'
        ax2.set_ylabel('d(Ownership)/dFPTS', color=color2)
        line2 = ax2.plot(fpts_min_list, deriv, 
                        marker='x', color=color2, label='Derivative')
        ax2.tick_params(axis='y', labelcolor=color2)

        # -- Combine legends from both axes
        lines = line1 + line2
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc='best')

        plt.title('Ownership vs. FPTS Minimum Constraint + Derivative')
        plt.grid(True)
        plt.show()



    def _run_fpts_owned_optimization(self, fpts_min, maximize=False):
        """
        Creates a fresh LP problem for each fpts_min and either 
        (a) Minimizes sum of ownership or 
        (b) Maximizes sum of ownership, subject to FPTS >= fpts_min.

        Returns the final sum of ownership from the optimized lineup 
        (or None if infeasible).
        """
        # Create a new problem
        prob_name = f"FPTS_{fpts_min:.2f}_{'MaxOwn' if maximize else 'MinOwn'}"
        if maximize:
            problem = plp.LpProblem(prob_name, plp.LpMaximize)
        else:
            problem = plp.LpProblem(prob_name, plp.LpMinimize)

        # Re-create LP variables. In practice, you might want to copy 
        # or re-initialize them to avoid clashes with older constraints.
        self.lp_variables = {}
        for player in self.players:
            for position in player.position:
                var_name = f"{player.name}_{position}_{player.id}_{prob_name}"
                self.lp_variables[(player, position)] = plp.LpVariable(
                    name=var_name, cat=plp.LpBinary
                )

        # Add constraints
        constraint_manager = ConstraintManager(
            self.site, problem, self.players, self.lp_variables, self.config
        )
        constraint_manager.add_static_constraints()

        # FPTS >= fpts_min constraint
        # sum of (player.fpts * x[p]) >= fpts_min
        problem += (
            lpSum(
                player.fpts * self.lp_variables[(player, position)]
                for player in self.players
                for position in player.position
            ) >= fpts_min,
            "MinFptsConstraint"
        )

        # Objective: sum of ownership
        ownership_expr = lpSum(
            player.ownership * self.lp_variables[(player, position)]
            for player in self.players
            for position in player.position
        )
        # If maximizing, set objective to ownership_expr; if minimizing, set to ownership_expr
        problem.setObjective(ownership_expr)

        # Solve
        try:
            problem.solve(plp.GLPK(msg=0))
        except plp.PulpSolverError:
            print(f"Infeasibility in {prob_name}.")
            return None

        # Check for solution
        if plp.LpStatus[problem.status] != "Optimal":
            print(f"No optimal solution for {prob_name}.")
            return None

        # Compute final ownership sum
        final_vars = [k for k, v in self.lp_variables.items() if v.varValue == 1]
        final_lineup = [(player, pos) for (player, pos) in final_vars]
        total_ownership = sum(player.ownership for (player, _) in final_lineup)

        return total_ownership



    def run(self):
        """
        Run the optimization process in two stages:
        1. Extract the baseline fpts and ownership from the first lineup.
        2. Use these baseline values to set constraints and maximize ceiling with added randomness.
        :return: Lineups instance containing optimized lineups.
        """
        lineups = Lineups()  # Object to store all generated lineups
        exclusion_constraints = []  # List to store uniqueness constraints
        
        randomness_factor = self.config.get("randomness_amount", 10) / 100  # Example: 10% randomness
        ceiling_weight = self.config.get("ceiling_weight", 1.0)
        ownership_weight = self.config.get("ownership_weight", 1.0)
        min_fpts = self.config.get("min_fpts")
        max_own = self.config.get("max_ownership")

    
        # Stage 3: Optimize subsequent lineups with added randomness
        for i in range(self.num_lineups):
            if i % 10 == 0: 
                print(i)
            self.problem = LpProblem(f"Stage2_NBA_DFS_Optimization_{i}", LpMaximize)

            for constraint in exclusion_constraints:
                self.problem += constraint

            # Reinitialize constraints for the new problem
            constraint_manager = ConstraintManager(
                self.site, self.problem, self.players, self.lp_variables, self.config
            )
            constraint_manager.add_static_constraints()
            constraint_manager.add_optional_constraints(min_fpts, max_own)

            sampled_ceiling_values = {}
            sampled_ownership_values = {}

            # Add randomness to ceiling values
            for player in self.players:
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


    

    






