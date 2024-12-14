import pandas as pd

def calculate_exposure(lineups, players):
    """
    Calculate player exposure in the given lineups and return a sorted DataFrame.

    :param lineups: List of lineups, where each lineup is a list of (player, position, player.id) tuples.
    :param players: List of all Player objects used in the lineups.
    :return: Pandas DataFrame sorted by exposure percentage, highest to lowest.
    """
    # Initialize a dictionary to track exposures
    exposure_count = {player.id: 0 for player in players}
    total_lineups = len(lineups)

    # Count the occurrences of each player in the lineups
    for lineup in lineups:
        for player_tuple in lineup:
            if isinstance(player_tuple[0], type(players[0])):  # Check if it's a Player object
                player_id = player_tuple[2]  # Extract `player.id` from the tuple
                exposure_count[player_id] += 1

    # Create a DataFrame with player data
    data = []
    for player in players:
        exposure = (exposure_count[player.id] / total_lineups) * 100
        data.append({
            "Name": player.name,
            "Team": player.team,
            "Salary": player.salary,
            "Exposure (%)": exposure,
            "Minutes": player.minutes,
            "Ownership": player.ownership,
            "Leverage": exposure - player.ownership,
            "FPTS": player.fpts,
            "Value": player.fpts / player.salary * 1000,
            "STDDEV": player.stddev,
            "Variance Score": player.stddev / player.fpts,
            "Boom": player.boom_pct,
            "Bust": player.bust_pct,
        })

    # Create and sort the DataFrame
    df = pd.DataFrame(data)
    df.sort_values(by="Exposure (%)", ascending=False, inplace=True)
    return df

