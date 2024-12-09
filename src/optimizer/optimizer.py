import pulp as plp
from lineups.lineup import Lineup, LineupPool

class Optimizer:
    def __init__(self, site, num_lineups, num_uniques, randomness_amount=0.0):
        self.site = site
        self.num_lineups = num_lineups
        self.num_uniques = num_uniques
        self.randomness_amount = randomness_amount
        self.players = []
        self.problem = plp.LpProblem("DFS_Optimization", plp.LpMaximize)

    def set_players(self, players):
        self.players = players

    def optimize(self):
        lp_variables = {
            player: plp.LpVariable(f"{player.name}", cat=plp.LpBinary) for player in self.players
        }

        # Objective function: Maximize fantasy points
        self.problem += plp.lpSum(
            player.fpts * lp_variables[player] for player in self.players
        ), "Maximize_Fantasy_Points"

        # Constraints
        self.add_constraints(lp_variables)

        # Solve the problem
        self.problem.solve(plp.PULP_CBC_CMD(msg=False))

        # Extract lineups
        return self.extract_lineups(lp_variables)

    def add_constraints(self, lp_variables):
        # Salary constraints
        self.problem += plp.lpSum(
            player.salary * lp_variables[player] for player in self.players
        ) <= 50000, "Max_Salary"
        self.problem += plp.lpSum(
            player.salary * lp_variables[player] for player in self.players
        ) >= 49000, "Min_Salary"

        # Unique lineups
        for i in range(self.num_uniques):
            self.problem += plp.lpSum(lp_variables[player] for player in self.players) <= len(self.players) - 1

    def extract_lineups(self, lp_variables):
        lineups = []
        for _ in range(self.num_lineups):
            selected_players = [player for player in self.players if lp_variables[player].varValue == 1]
            if selected_players:
                lineups.append(Lineup(selected_players))
        return LineupPool(lineups)
