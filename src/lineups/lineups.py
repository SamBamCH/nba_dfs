import numpy as np

class Lineups:
    def __init__(self):
        self.lineups = []

    def add_lineup(self, lineup):
        """Add a new lineup to the collection."""
        formatted_lineup = [
            (player, pos, player.id) for player, pos in lineup
        ]
        self.lineups.append(formatted_lineup)

    def sort_lineup(self, lineup, site):
        """Sort a lineup by position based on the site-specific rules."""
        if site == "dk":
            order = ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]
            sorted_lineup = [None] * 8
        else:
            order = ["PG", "PG", "SG", "SG", "SF", "SF", "PF", "PF", "C"]
            sorted_lineup = [None] * 9

        for player, pos, _ in lineup:
            order_idx = order.index(pos)
            if sorted_lineup[order_idx] is None:
                sorted_lineup[order_idx] = (player, pos)
            else:
                sorted_lineup[order_idx + 1] = (player, pos)
        return sorted_lineup

    def export_to_csv(self, file_path, site):
        """Export the lineups to a CSV file."""
        with open(file_path, "w") as f:
            if site == "dk":
                f.write(
                    "PG,SG,SF,PF,C,G,F,UTIL,Salary,Fpts Proj,Own. Prod.,Own. Sum.,Minutes,StdDev\n"
                )
            else:
                f.write(
                    "PG,PG,SG,SG,SF,SF,PF,PF,C,Salary,Fpts Proj,Own. Prod.,Own. Sum.,Minutes,StdDev\n"
                )
            for lineup in self.lineups:
                salary = sum(player.salary for player, _, _ in lineup)
                fpts_p = sum(player.fpts for player, _, _ in lineup)
                own_p = np.prod([player.ownership / 100 for player, _, _ in lineup])
                own_s = sum(player.ownership for player, _, _ in lineup)
                mins = sum(player.minutes for player, _, _ in lineup)
                stddev = sum(player.stddev for player, _, _ in lineup)

                lineup_str = ",".join(
                    [f"{player.name} ({player.id})" for player, _, _ in lineup]
                )
                f.write(
                    f"{lineup_str},{salary},{round(fpts_p, 2)},{own_p},{own_s},{mins},{stddev}\n"
                )

    def __len__(self):
        return len(self.lineups)

