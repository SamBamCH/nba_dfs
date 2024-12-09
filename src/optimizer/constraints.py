from pulp import lpSum


class ConstraintManager:
    def __init__(self, site, problem, players, lp_variables, config):
        """
        Initialize ConstraintManager with relevant details.
        :param site: The platform (e.g., 'dk' or 'fd').
        :param problem: The optimization problem instance.
        :param players: List of Player objects.
        :param lp_variables: Dictionary of LP variables.
        :param config: Configuration dictionary with limits and rules.
        """
        self.site = site
        self.problem = problem
        self.players = players
        self.lp_variables = lp_variables
        self.config = config

    def add_salary_constraints(self):
        max_salary = 50000 if self.site == "dk" else 60000
        min_salary = self.config.get("min_salary", 49000 if self.site == "dk" else 59000)

        # Add max salary constraint with a unique name
        self.problem += lpSum(
            player.salary * self.lp_variables[(player, position)]
            for player in self.players
            for position in player.position
        ) <= max_salary, f"Max_Salary_{self.site}"

        # Add min salary constraint with a unique name
        self.problem += lpSum(
            player.salary * self.lp_variables[(player, position)]
            for player in self.players
            for position in player.position
        ) >= min_salary, f"Min_Salary_{self.site}"

    def add_position_constraints(self):
        position_limits = {
            "PG": 2, "SG": 2, "SF": 2, "PF": 2, "C": 1
        } if self.site == "fd" else {
            "PG": 1, "SG": 1, "SF": 1, "PF": 1, "C": 1, "G": 1, "F": 1, "UTIL": 1
        }

        for pos, limit in position_limits.items():
            eligible_players = [
                (player, pos) for player in self.players if pos in player.position
            ]
            self.problem += lpSum(
                self.lp_variables[key] for key in eligible_players
            ) == limit, f"Position_Constraint_{pos}_{self.site}"

    def add_team_constraints(self):
        team_limits = self.config.get("team_limits", {})
        for team, limit in team_limits.items():
            eligible_players = [
                (player, position)
                for player in self.players
                for position in player.position
                if player.team == team
            ]
            self.problem += lpSum(
                self.lp_variables[key] for key in eligible_players
            ) <= limit, f"Team_Limit_{team}_{self.site}"

        # Global team limit
        global_team_limit = self.config.get("global_team_limit")
        if global_team_limit:
            for team in set(player.team for player in self.players):
                eligible_players = [
                    (player, position)
                    for player in self.players
                    for position in player.position
                    if player.team == team
                ]
                self.problem += lpSum(
                    self.lp_variables[key] for key in eligible_players
                ) <= global_team_limit, f"Global_Team_Limit_{team}_{self.site}"

    def add_matchup_constraints(self):
        matchup_limits = self.config.get("matchup_limits", {})
        for matchup, limit in matchup_limits.items():
            eligible_players = [
                (player, position)
                for player in self.players
                for position in player.position
                if player.matchup == matchup
            ]
            self.problem += lpSum(
                self.lp_variables[key] for key in eligible_players
            ) <= limit, f"Matchup Limit: {matchup} <= {limit}"

        matchup_at_least = self.config.get("matchup_at_least", {})
        for matchup, min_players in matchup_at_least.items():
            eligible_players = [
                (player, position)
                for player in self.players
                for position in player.position
                if player.matchup == matchup
            ]
            self.problem += lpSum(
                self.lp_variables[key] for key in eligible_players
            ) >= min_players, f"Matchup At Least: {matchup} >= {min_players}"

    def add_player_constraints(self):
        # At-most constraints
        at_most = self.config.get("at_most", {})
        for max_limit, player_groups in at_most.items():
            for group in player_groups:
                eligible_players = [
                    (player, position)
                    for player in self.players
                    for position in player.position
                    if player.name in group
                ]
                self.problem += lpSum(
                    self.lp_variables[key] for key in eligible_players
                ) <= max_limit, f"At Most {max_limit} Players from Group"

        # At-least constraints
        at_least = self.config.get("at_least", {})
        for min_limit, player_groups in at_least.items():
            for group in player_groups:
                eligible_players = [
                    (player, position)
                    for player in self.players
                    for position in player.position
                    if player.name in group
                ]
                self.problem += lpSum(
                    self.lp_variables[key] for key in eligible_players
                ) >= min_limit, f"At Least {min_limit} Players from Group"

    def add_uniqueness_constraint(self, lineup, num_uniques, iteration):
        """
        Add a uniqueness constraint for the given lineup.
        :param lineup: List of tuples (player, position) in the lineup.
        :param num_uniques: Minimum number of unique players between lineups.
        :param iteration: Current iteration number for generating lineups.
        """
        overlap_constraint = f"Uniqueness_Constraint_{iteration}"
        self.problem += (
            lpSum(self.lp_variables[(player, position)] for player, position in lineup) <= len(lineup) - num_uniques,
            overlap_constraint
        )

    def enforce_lineup_uniqueness(self, selected_lineups, num_uniques):
        """
        Ensure at least `num_uniques` players differ between the new lineup and any existing lineup.
        :param selected_lineups: List of already generated lineups.
        :param num_uniques: Minimum number of unique players required between lineups.
        """
        for i, existing_lineup in enumerate(selected_lineups):
            overlap_constraint = f"Enforce_Uniqueness_{i}"
            self.problem += (
                lpSum(self.lp_variables[(player, position)] for player, position in existing_lineup)
                <= len(existing_lineup) - num_uniques,
                overlap_constraint
            )

    def add_single_player_selection_constraint(self):
        """
        Ensure each player can only be selected once per lineup, across all positions.
        """
        for player in self.players:
            eligible_positions = [
                (player, position) for position in player.position
            ]
            self.problem += lpSum(
                self.lp_variables[key] for key in eligible_positions
            ) <= 1, f"Single Selection Constraint for {player.name}"

    def add_all_constraints(self, selected_lineups, num_uniques):
        """
        Add all static constraints (salary, position, team) to the problem.
        """
        self.add_salary_constraints()
        self.add_position_constraints()
        self.add_team_constraints()
        self.add_matchup_constraints()
        self.add_player_constraints()
        self.add_single_player_selection_constraint()
