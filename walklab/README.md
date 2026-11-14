# Professional demo review routes

Walklab includes review-only routes extracted from the MOUZ NXT vs URSA match
2393178 demos in `data/pro_demos/2393178/`. Choose Dust2 or Mirage, then select
a named route under **职业 demo 轨迹**. Playback uses recorded world positions and
view angles; keyboard input is intentionally empty. The timeline, 3D view,
route line, rename control, and JSON export all work for these imported routes.
Renames are saved in this browser and included in exported JSON. The original
demo, player, round, ticks, and SHA-256 remain in `source`.

The source files are:

- Dust2: `mouz-nxt-vs-ursa-m1-dust2.dem`
- Mirage: `mouz-nxt-vs-ursa-m2-mirage.dem`

`scripts/pro_demo_walklab.py` samples living players every four demo ticks
(16 Hz at 64 ticks/s), converts positions and angles into the platform map
coordinate system, and retains a route only when that player did not die
between its first and last frame. Gunfire and damage are allowed. Each frame
preserves the player's yaw and pitch so the first-person playback shows the
original pre-aim and fight angles. This does not prove that the route is
collision-safe in a live match. The catalog is for visual review; it is not
registered in `agent.py`.

Regenerate with `demoparser2==0.42.2` installed:

```sh
python3 -m scripts.pro_demo_walklab \
  data/pro_demos/2393178/mouz-nxt-vs-ursa-m1-dust2.dem \
  tests/fixtures/dust2_static.json walklab/public/routes/dust2-pro.json
python3 -m scripts.pro_demo_walklab \
  data/pro_demos/2393178/mouz-nxt-vs-ursa-m2-mirage.dem \
  walklab/src/map-fixtures/mirage_static.json \
  walklab/public/routes/mirage-pro.json
```

The catalog selects at most two surviving examples per tactical category from
this match. Categories without a surviving example are left empty; an
unrelated path is never relabeled to fill them.

## Two-stage review

The catalog also has independent CT hold windows after the player reaches a
defensive area, and T post-plant hold windows. Each hold window spans about
6-8 seconds, stays near its named area, shows actual recorded movement and
view angles, and contains no player death. Dust2 has CT holds for A, A short,
mid doors and B; Mirage has CT holds for A, connector, mid and B. Both maps
have T post-plant holds for A and B.

The **two-stage combination** selector pairs CT opening with a CT hold in
the same area, or T attack with a T post-plant hold at the same site. It only
offers a hold as a loop when the first and last poses are within 2.5 m. The
JSON export for a selected combination is a `walklab-combination-v1` manifest
containing the two source route IDs, transition condition, join distance and
loop closure distance. Source routes remain individually reviewable and
exportable.

Walklab preview switches poses directly at the stage boundary and at each
loop boundary; it does not move through the gap. In an agent, the first stage
must hand off to live navigation toward the hold start. CT can enter the hold
after arriving in its assigned area. T must finish its plant handoff and
observe the bomb planted before entering the post-plant hold. Loop completion
requires moving back toward the first hold pose, not teleporting to it.
These combinations are review data, not registered agent strategy options.
