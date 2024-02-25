# NBAFantasyOptimizer

Optimization solver to play the NBA Fantasy game Salary Cap Edition. It generates optimal squads for a set of gamedays as well as optimal transfers for your team.

### Data

Two csvs files are available in this repository:

- players.csv: list of all the NBA players with their average fantasy points per game.
- games.csv: list containing every game of the regular season, including teams, date and gameday.

### Configuration

JSON file to introduce inputs to the optimizer.

You can control the gamedays you want to optimize for, number of transfers and budget available.

Initial squad can be left empty, in that case the code will select the optimal players given the budget. 

It is also possible to adjust the player points to be used in the objective function. In the example, Joel Embiid's points are set to 0 because he is injured.

Example:

```
{
  "budget": 1010,
  "start_gameday": 110,
  "end_gameday": 113,
  "transfers": 2,
  "initial_squad": [
    "Giannis Antetokounmpo",
    "Luka Doncic",
    "Toumani Camara",
    "Shai Gilgeous-Alexander",
    "Jalen Wilson",
    "Marcus Sasser",
    "Vince Williams Jr.",
    "Payton Pritchard",
    "Jalen Johnson",
    "Anthony Davis"
  ],
  "player_points_adjustments": {
    "Joel Embiid": 0.0,
    "Ja Morant": 0.0
  }
}
```
