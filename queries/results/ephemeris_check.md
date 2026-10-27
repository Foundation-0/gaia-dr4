# Does the DR3 ephemeris predict the eclipses in the star's own light curve?

The 10 brightest DR3 binaries with a period over 100 days, a TWOGAUSSIANS model, a primary depth of 0.3 to 3 mag, a primary duration of 0.05 to 0.3 of the period and global_ranking above 0.4 (rules fixed before looking). Rank 1 means the predicted window is the faintest of 50 windows round the phase circle.

| source_id | G | period (d) | G points | in predicted window | dimming inside minus outside (mag) | table depth (mag) | rank, table phase | rank, reversed phase | rank, phase + 0.5 |
|---|---|---|---|---|---|---|---|---|---|
| 6657628225713981312 | 6.97 | 232.8 | 50 | 11 | +0.00 | 0.50 | 29 | 37 | 8 |
| 934991913366424320 | 7.59 | 150.3 | 34 | 9 | +0.18 | 2.74 | 9 | 19 | 10 |
| 6714545578996082304 | 7.66 | 107.4 | 19 | 8 | +0.25 | 0.32 | 4 | 13 | 13 |
| 4316162208049061888 | 7.94 | 108.6 | 42 | 4 | -0.08 | 0.83 | 23 | 1 | 2 |
| 6071092098645364224 | 8.02 | 198.4 | 55 | 13 | +0.28 | 0.79 | 3 | 37 | 15 |
| 6138160619976665728 | 9.27 | 150.0 | 25 | 7 | +0.23 | 1.39 | 6 | 18 | 18 |
| 1916472857688579712 | 10.05 | 151.0 | 52 | 14 | +0.24 | 1.33 | 6 | 25 | 12 |
| 3518398798991565184 | 10.18 | 203.8 | 61 | 6 | +0.25 | 0.83 | 5 | 36 | 1 |
| 2720039248534841472 | 10.40 | 106.6 | 28 | 13 | +0.16 | 2.84 | 11 | 29 | 3 |
| 3437789340956759552 | 10.41 | 107.0 | 28 | 8 | +0.35 | 1.25 | 4 | n/a | 9 |

Predicted window among the 5 faintest of 50: **4 of 10 stars** with the table's phase, 1 with the sign of the phase reversed, 3 at phase plus 0.5. Among the 11 faintest of 50 (22 per cent): 8 with the table's phase, 1 with the sign reversed. Median rank: 6 with the table's phase, 25 reversed. Chance alone gives 1.0 stars in the top 5 and 2.2 in the top 11 (10 stars times 11 of 50 windows), and a median rank near 25. n/a means the window held too few points to rank.

Each window holds only a few points, because Gaia observes a given star about once every 20 to 30 days on average, and in several stars the dimming rests on one or two visits. This is a weak test of the phase convention. It says nothing about whether the period is right to a fraction of a cycle over 100 years.
