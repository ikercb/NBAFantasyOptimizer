import pulp
import pandas as pd
import requests
import json


class NBAFantasyOptimizer:
    INITIAL_PLAYERS_COUNT = 10
    MIN_PLAYER_TYPE_COUNT = 2
    PLAYER_TYPE_COUNT = 5
    TOTAL_PLAYERS_PER_DAY = 5
    MAX_PLAYERS_FROM_SAME_TEAM = 2

    def __init__(self, players_df, games_df, config):
        self.players_df = players_df
        self.games_df = games_df
        self.config = config
        self.prob = pulp.LpProblem("NBAFantasy", pulp.LpMaximize)

    def setup_problem(self):
        self.budget = self.config["budget"]
        self.start_gameday = self.config["start_gameday"]
        self.end_gameday = self.config["end_gameday"]

        self.days = range(self.start_gameday, self.end_gameday + 1)

        if "player_points_adjustments" in self.config:
            self.adjust_player_points()

        self.initialize_variables()
        self.add_constraints()
        self.set_objective_function()

        # Solve
        self.prob.solve()
        self.print_solution()

    def initialize_variables(self):
        # Binary variable that records whether a player is in the initial squad
        self.initial_squad = pulp.LpVariable.dicts(
            "initial_squad", [i for i in self.players_df.index], cat="Binary"
        )
        # Binary variable that records whether a player is in the squad on day d
        self.squad_day = pulp.LpVariable.dicts(
            "squad_day",
            [(i, d) for i in self.players_df.index for d in self.days],
            cat="Binary",
        )
        # Binary variable that records whether a player is in the line-up on day d
        self.chosen_day = pulp.LpVariable.dicts(
            "player_day",
            [(i, d) for i in self.players_df.index for d in self.days],
            cat="Binary",
        )
        # Binary variable that records whether a player is transferred in on day d
        self.t_in = pulp.LpVariable.dicts(
            "transfer_in",
            [(i, d) for i in self.players_df.index for d in self.days],
            cat="Binary",
        )
        # Binary variable that records whether a player is transferred out on day d
        self.t_out = pulp.LpVariable.dicts(
            "transfer_out",
            [(i, d) for i in self.players_df.index for d in self.days],
            cat="Binary",
        )
        # Binary variable that records which player is selected as captain
        self.doubled_score = pulp.LpVariable.dicts(
            "captain_selected",
            [(i, d) for i in self.players_df.index for d in self.days],
            cat="Binary",
        )

    def adjust_player_points(self):
        for player_name, points in self.config["player_points_adjustments"].items():
            if player_name in self.players_df["name"].values:
                self.players_df.loc[
                    self.players_df["name"] == player_name, "points_per_game"
                ] = points
            else:
                print(f"Warning: Player '{player_name}' not found in DataFrame.")

    def add_constraints(self):
        self.add_initial_player_constraints()
        self.add_budget_constraints()
        self.add_transfer_constraints()
        self.add_daily_constraints()
        self.add_team_constraints()

    def add_initial_player_constraints(self):
        # 10 initial players for the week
        self.prob += (
            pulp.lpSum(self.initial_squad[i] for i in self.players_df.index)
            == self.INITIAL_PLAYERS_COUNT
        )

        # This function sets the constraints for the initial players
        for player_name in self.config["initial_squad"]:
            player_index = self.players_df[
                self.players_df["name"] == player_name
            ].index[0]
            self.initial_squad[player_index].upBound = 1
            self.initial_squad[player_index].lowBound = 1

    def add_budget_constraints(self):
        # Set initial squad budget constraint
        self.prob += (
            pulp.lpSum(
                [
                    self.initial_squad[i] * self.players_df["now_cost"][i]
                    for i in self.players_df.index
                ]
            )
            <= self.config["budget"],
            f"Inital Squad Budget",
        )

        # Sets budget constraints for each day
        for d in self.days:
            self.prob += (
                pulp.lpSum(
                    [
                        self.squad_day[i, d] * self.players_df["now_cost"][i]
                        for i in self.players_df.index
                    ]
                )
                <= self.config["budget"],
                f"Budget Day {d}",
            )

    def add_transfer_constraints(self):
        # Sets transfer limits and consistency constraints
        # Limit on transfers
        self.prob += pulp.lpSum(self.t_in) <= self.config["transfers"]
        self.prob += pulp.lpSum(self.t_out) <= self.config["transfers"]

        # Transfer consistency
        for i in self.players_df.index:
            for d in self.days:
                if d == self.start_gameday:
                    # Compare with initial squad
                    self.prob += (
                        self.t_in[i, d] >= self.squad_day[i, d] - self.initial_squad[i],
                        f"Transfer_In_Consistency_{i}_{d}",
                    )
                    self.prob += (
                        self.t_out[i, d]
                        >= self.initial_squad[i] - self.squad_day[i, d],
                        f"Transfer_Out_Consistency_{i}_{d}",
                    )
                else:
                    self.prob += (
                        self.t_in[i, d]
                        >= self.squad_day[i, d] - self.squad_day[i, d - 1],
                        f"Transfer_In_Consistency_{i}_{d}",
                    )
                    self.prob += (
                        self.t_out[i, d]
                        >= self.squad_day[i, d - 1] - self.squad_day[i, d],
                        f"Transfer_Out_Consistency_{i}_{d}",
                    )

    def add_daily_constraints(self):
        # Sets constraints that apply to each day
        for d in self.days:
            # Constraints based on player types and total players chosen
            self.prob += (
                pulp.lpSum(
                    [
                        self.chosen_day[(i, d)]
                        for i in self.players_df[
                            self.players_df["element_type"] == 1
                        ].index
                    ]
                )
                >= self.MIN_PLAYER_TYPE_COUNT
            )
            self.prob += (
                pulp.lpSum(
                    [
                        self.chosen_day[(i, d)]
                        for i in self.players_df[
                            self.players_df["element_type"] == 2
                        ].index
                    ]
                )
                >= self.MIN_PLAYER_TYPE_COUNT
            )
            self.prob += (
                pulp.lpSum([self.chosen_day[(i, d)] for i in self.players_df.index])
                == self.TOTAL_PLAYERS_PER_DAY
            )
            self.prob += (
                pulp.lpSum([self.doubled_score[(i, d)] for i in self.players_df.index])
                == 1
            )

            # Squad size constraints
            self.prob += (
                pulp.lpSum(
                    [
                        self.squad_day[(i, d)]
                        for i in self.players_df[
                            self.players_df["element_type"] == 1
                        ].index
                    ]
                )
                == self.PLAYER_TYPE_COUNT
            )
            self.prob += (
                pulp.lpSum(
                    [
                        self.squad_day[(i, d)]
                        for i in self.players_df[
                            self.players_df["element_type"] == 2
                        ].index
                    ]
                )
                == self.PLAYER_TYPE_COUNT
            )

            for i in self.players_df.index:
                # Players can't play on a day if they're not chosen for the week
                self.prob += self.chosen_day[(i, d)] <= self.squad_day[(i, d)]
                self.prob += self.doubled_score[(i, d)] <= self.chosen_day[(i, d)]

    def add_team_constraints(self):
        # Two players from the same team constraint
        for team in self.players_df["team"].unique():
            for d in self.days:
                self.prob += (
                    pulp.lpSum(
                        self.squad_day[i, d]
                        for i in self.players_df[self.players_df["team"] == team].index
                    )
                    <= self.MAX_PLAYERS_FROM_SAME_TEAM
                )

    def set_objective_function(self):
        # Define the function that calculates player points for a day
        def player_points_for_day(player_idx, day):
            team = self.players_df["team"][player_idx]
            games_on_day = self.games_df[self.games_df["event"] == day]

            if (
                team in games_on_day["team_h"].values
                or team in games_on_day["team_a"].values
            ):
                return self.players_df["points_per_game"].astype(float)[player_idx]
            return 0

        # Set the objective function
        self.prob += pulp.lpSum(
            player_points_for_day(i, d)
            * (self.chosen_day[(i, d)] + self.doubled_score[(i, d)])
            for i in self.players_df.index
            for d in self.days
        )

    def print_initial_squad(self):
        print("Initial Squad:")
        for player_idx in self.players_df.index:
            if self.initial_squad[player_idx].varValue == 1:
                player_name = self.players_df.loc[player_idx, "name"]
                print(f"  - {player_name}")

    def print_solution(self):
        if self.prob.status != pulp.LpStatusOptimal:
            print("No optimal solution found.")
            return

        # Print the value of the objective function
        print(f"Total Points: {pulp.value(self.prob.objective)}")

        # Print the transfers to be made
        print("\nTransfers to be made:")
        for d in self.days:
            transfers_in = [
                (i, d)
                for i in self.players_df.index
                if pulp.value(self.t_in[i, d]) == 1
            ]
            transfers_out = [
                (i, d)
                for i in self.players_df.index
                if pulp.value(self.t_out[i, d]) == 1
            ]

            if transfers_in or transfers_out:
                print(f"\nDay {d}:")
                if transfers_in:
                    print("  Transfers In:")
                    for i, day in transfers_in:
                        player_name = self.players_df.loc[i, "name"]
                        print(f"    - {player_name}")

                if transfers_out:
                    print("  Transfers Out:")
                    for i, day in transfers_out:
                        player_name = self.players_df.loc[i, "name"]
                        print(f"    - {player_name}")


def main():
    # Read configuration file
    with open("config.json", "r") as file:
        config = json.load(file)

    # Read players dataframe
    players_df = pd.read_csv("players.csv")

    # Read games dataframe
    games_df = pd.read_csv("games.csv")

    # Create optimizer object and run solver
    optimizer = NBAFantasyOptimizer(players_df, games_df, config)
    optimizer.setup_problem()
    optimizer.print_initial_squad()


if __name__ == "__main__":
    main()
