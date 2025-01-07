import os
from data.data_manager import DataManager
from optimizer.optimizer import Optimizer
from lineups.lineups import Lineups
from lineups.lineup_metrics import calculate_exposure
from optimizer.late_swaptimizer import LateSwaptimizer
import pandas as pd
from data.database import initialize_database, write_players_to_database

### Entry point of the application

def main():
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    initialize_database()
    # Initialize DataManager for the desired site (e.g., 'dk')
    site = "dk"  # Or "fd" depending on the use case
    process = 'main'


    data_manager = DataManager(site)

    # Load player data
    try:
        data_manager.load_player_data()
        print("Player data loaded successfully.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # Filter out invalid players and capture removed players
    removed_players = [
        player for player in data_manager.players
        if player.id in [0, None]
    ]
    print("Players removed before optimizer initialization:")
    for player in removed_players:
        print(f"Name: {player.name}, Ownership: {player.ownership}, ID: {player.id}")

    players = [
        player for player in data_manager.players
        if player.fpts > data_manager.config.get("projection_minimum")
    ]

    write_players_to_database(players)
    print("Player data saved to the database.")

    ### up to this point, the optimization process is the exact same, assuming that the projections, boom_bust, and player_ids are all the same format. 

    # Initialize the optimizer
    if process == 'main':
        contest_params_dict = data_manager.config.get("contest_params", {})

        for contest_style, c_params in contest_params_dict.items():
            print(f"\n=== Building lineups for: {contest_style} ===")

            num_lineups = c_params.get("num_lineups", 5)
            num_uniques = c_params.get("num_uniques", 1)
            data_manager.config["ceiling_weight"] = c_params.get("ceiling_weight", 3)
            data_manager.config["ownership_weight"] = c_params.get("ownership_weight", 1)
            data_manager.config["max_ownership_sum"] = c_params.get("max_ownership_sum", 999)
            data_manager.config["min_fpts"] = c_params.get("min_fpts", 0)

            optimizer = Optimizer(
                    site=site,
                    players=players,
                    num_lineups=num_lineups,
                    num_uniques=num_uniques,
                    config=data_manager.config
                )
            # Generate lineups
            lineups = optimizer.run()

            # Print exposures or any other info
            exposure_df = calculate_exposure(lineups.lineups, players)
            print(exposure_df)

            # Optionally, export to a unique file for each contest type
            filename = f"C:/Users/samba/nba_dfs/data/output/optimal_lineups_{contest_style}.csv"
            lineups.export_to_csv(filename, site=optimizer.site)

    else :
        data_manager.populate_ids_to_gametime()
        data_manager.load_player_lineups(data_manager.config['late_swap_path'])
        late_swap = LateSwaptimizer(site, players, data_manager.config, data_manager.lineups)
        lineups = late_swap.run(output_csv_path="C:/Users/samba/nba_dfs/data/output/swapped_lineups.csv")

        exposure_df = calculate_exposure(lineups.lineups, players)
        print(exposure_df)

        # for lineup in data_manager.lineups:
        #     print(lineup)
            ### {'entry_id': '4561617468', 'contest_id': '171700955', 'contest_name': 'DFS Hero - Friday Night Hoops by Momar89', 'PG': 'Vasilije Micic (37001127)', 'SG': 'Brandon Miller (37000948)', 'SF': 'Justin Champagnie (37001198) (LOCKED)', 'PF': 'Miles Bridges (37001074)', 'C': 'Jalen Smith (37001372)', 'G': 'Kevin Porter Jr. (37001233)', 'F': 'Bilal Coulibaly (37001115) (LOCKED)', 'UTIL': 'Nikola Jokic (37000929)', 'PG_is_locked': False, 'SG_is_locked': False, 'SF_is_locked': True, 'PF_is_locked': False, 'C_is_locked': False, 'G_is_locked': False, 'F_is_locked': True, 'UTIL_is_locked': False}


if __name__ == "__main__":
    main()

#------CONCEPTUALIZING------#
#TODO: add different parameters for different contests (SE, 3-max, 20-max, 150-max), and loop them through the optimizer, creating a unique output for each loop. We can add a parameter to the config file that takes the requetsed number of unique lineups from each style of the optimization. 
#TODO: add 'entry editor' style
    ### different weights for different contests? i.e. closer to optimal in SE, more variability in optimization for MME. 
#TODO: live ownership from contests
#TODO: infer unlocked player ownership
#TODO: boost for player's ceilings who are starting? seems like stok projects the starters for less min in uncertain spots. 
#TODO: clean up logic of derivative for finding optimal limit. it's fine currently, but could be better. 
#TODO: better way to dial in ownership max constraint. Right now, can use it to avoid being super chalky, but that's about it. 
#TODO: redundant config definition in the loop. 

#------TEST------#
#TODO: complexify lateswap with the same parameters as prelock
    ###need to test after lock. Can't verify with simulated time. 