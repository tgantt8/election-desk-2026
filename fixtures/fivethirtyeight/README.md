# FiveThirtyEight pollster-ratings raw polls (subset)

`raw-polls_2018-2022_senate-governor.csv` is a column-and-row subset of FiveThirtyEight's `pollster-ratings/2023/raw-polls.csv`
(https://github.com/fivethirtyeight/data/tree/master/pollster-ratings), fetched 2026-10-29 from
https://raw.githubusercontent.com/fivethirtyeight/data/master/pollster-ratings/2023/raw-polls.csv.
Rows: year 2018 and 2022, `type_simple` Sen-G and Gov-G (general-election Senate and Governor polls), with the official
result columns (`cand1_actual`, `cand2_actual`, `margin_actual`) FiveThirtyEight attached to each poll.
License: Creative Commons Attribution 4.0 International (the repository's LICENSE). Used only to backtest the simulator's
error model against real 2018 and 2022 outcomes; nothing here is shown as 2026 data.
