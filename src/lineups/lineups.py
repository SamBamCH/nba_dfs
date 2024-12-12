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

        for player, pos, player_id in lineup:
            order_idx = order.index(pos)
            if sorted_lineup[order_idx] is None:
                sorted_lineup[order_idx] = (player, pos, player_id)
            else:
                # Find the next available slot for this position
                next_idx = order_idx + 1
                while next_idx < len(sorted_lineup) and sorted_lineup[next_idx] is not None:
                    next_idx += 1
                if next_idx < len(sorted_lineup):
                    sorted_lineup[next_idx] = (player, pos, player_id)

        return [slot for slot in sorted_lineup if slot is not None]  # Remove None values


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
                # Sort the lineup according to the site's position order
                sorted_lineup = self.sort_lineup(lineup, site)

                # Calculate aggregate stats
                salary = sum(player.salary for player, _, _ in sorted_lineup)
                fpts_p = sum(player.fpts for player, _, _ in sorted_lineup)
                own_p = np.prod([player.ownership / 100 for player, _, _ in sorted_lineup])
                own_s = sum(player.ownership for player, _, _ in sorted_lineup)
                mins = sum(player.minutes for player, _, _ in sorted_lineup)
                stddev = sum(player.stddev for player, _, _ in sorted_lineup)

                # Create the lineup string
                lineup_str = ",".join(
                    [f"{player.name} ({player.id})" for player, _, _ in sorted_lineup]
                )
                f.write(
                    f"{lineup_str},{salary},{round(fpts_p, 2)},{own_p},{own_s},{mins},{stddev}\n"
                )


    def __len__(self):
        return len(self.lineups)


