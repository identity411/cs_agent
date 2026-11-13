# Dust2 / Mirage professional demo rotations

Integrated in [1113-v0.14](../submissions/1113-v0.14/README.md): main v10 and account2 v13, both admitted and activated. Match performance remains unverified.

Source: [MOUZ NXT vs URSA, match 2393178](https://www.hltv.org/matches/2393178/mouz-nxt-vs-ursa-nodwin-clutch-series-7) mirrored in the [OpenCS2 demo dataset](https://huggingface.co/datasets/blanchon/opencs2_dataset_demo). The local files are under `data/pro_demos/2393178/` (ignored by Git):

| Map | Demo | SHA-256 | Map fixture and geometry hash |
| --- | --- | --- | --- |
| Dust2 | `mouz-nxt-vs-ursa-m1-dust2.dem` | `caf5040a067d3bd2bb4e724c412fac2e75e3a10a6f3ddcad417321b07c28764d` | `tests/fixtures/dust2_static.json`, `b0c308526d55e56e3a50a5ecf9bdd1b70a02daf560a9a8157931f3b340fb8d66` |
| Mirage | `mouz-nxt-vs-ursa-m2-mirage.dem` | `bd006dbdbc90a077cb5cf059bb39b51b25b8e35751fa14fab468a5619e4dd299` | `walklab/src/map-fixtures/mirage_static.json`, `ef9384945046620f3f61ac579ae91f0beac8d5541c871e1996faf7a36f2e39db` |

`scripts/pro_demo_routes.py` uses `demoparser2==0.42.2` to sample CT player positions and view angles every four demo ticks. Valve source coordinates `(X,Y,Z)` map to platform coordinates `(100+Y*0.0254, 100+X*0.0254, 20+Z*0.0254)`. It finds A-to-B and B-to-A rotations during planted rounds, including the 20 seconds before the plant. The output keeps each sampled position, yaw, pitch, tick, player and round. The demo header map name is checked against the fixture ID.

| Map | Direction | Candidates | Highest forward-aim candidate (player, round, ticks, fraction) |
| --- | --- | ---: | --- |
| Dust2 | A to B | 7 | Alv, R21, 154440-156120, 0.995 |
| Dust2 | B to A | 6 | ay0k, R30, 227392-229228, 0.977 |
| Mirage | A to B | 6 | Alv, R7, 58992-62296, 0.858 |
| Mirage | B to A | 3 | Salazar, R4, 25844-27044, 0.956 |

The full candidate sets are `data/pro_demos/2393178/dust2_routes.json` and `mirage_routes.json`. `aim_forward_fraction` counts moving samples with pitch within 35 degrees and yaw within 85 degrees of travel direction. It is a **screening proxy**, not a check that the crosshair covers every corner or enemy entrance. Speed is retained only through original ticks and is not a prescribed agent movement speed. The demo's CS2 patch and the FPS fixture are different builds; the coordinate conversion has been checked against site positions, but each route still needs collision and navigation validation before use in a match.

## Agent integration

`scripts/build_pro_retakes.py` compiles candidates scoring at least 0.8 into `pro_retakes.py`: three routes for each Dust2 direction, three Mirage A-to-B and two Mirage B-to-A. The generated angles convert CS2 degrees to the FPS runtime's yaw/pitch radians; recorded tick timing is discarded. Every selected sample is within 2.7 m of a fixture nav node.

When a live CT near A or B sees a plant at the opposite site, `agent.py` selects the route whose start is closest to the CT's current position. Map ID and geometry hash must both match. Position feedback steers along the complete route with sprint requested on every movement action while the recorded view angles guide the crosshair. A visible enemy pauses movement and uses the existing combat logic; the route resumes after combat memory clears. The agent directly joins the route and, after its final frame, directly approaches the live bomb position for defusal. Low remaining fuse time does not change this behavior. A* is used only when no matching route is available or the agent actually becomes stuck.

To regenerate, install the parser into a Python environment, then run:

```sh
python3 scripts/pro_demo_routes.py data/pro_demos/2393178/mouz-nxt-vs-ursa-m1-dust2.dem tests/fixtures/dust2_static.json data/pro_demos/2393178/dust2_routes.json
python3 scripts/pro_demo_routes.py data/pro_demos/2393178/mouz-nxt-vs-ursa-m2-mirage.dem walklab/src/map-fixtures/mirage_static.json data/pro_demos/2393178/mirage_routes.json
```
