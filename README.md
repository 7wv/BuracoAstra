# Buraco CLI — Design Specification

## Run the game

The CLI and single-page browser GUI are implemented using the same Python rules engine. Python 3.10 or newer is required; there are no third-party dependencies.

- **Windows CLI:** double-click `play_cli.cmd`.
- **Windows browser GUI:** double-click `play_browser.cmd`. Keep its terminal open while playing. The game opens at `http://127.0.0.1:8765`.
- The launchers try installed Python first and can also use the bundled Codex Python runtime on this machine.

From a terminal in this folder, with Python installed:

```powershell
python -m buraco
python -m buraco.web
```

The browser server accepts `--port 8766` to use a different port and `--no-browser` to skip automatically opening a browser. It listens only on this computer. Each server process holds one shared hand in memory; refreshing the page reconnects to it, while stopping the server discards it. This is a shared-screen game with four human players, not network multiplayer.

In the browser, select cards and choose **Lay meld**, or click a target under **Add to your team's meld** and choose **Add cards**. A target may be chosen before drawing, but adding cards requires drawing or taking the discard pile first; the interface explains unavailable actions. Cards acquired during the turn have a gold outline and a **NEW** badge until played or the turn ends. Use **Queue meld** to stage separate melds for a single opening play, then **Play melds**. Select one card for **Discard & end turn**. Failed moves preserve the table and selections. **End hand** asks for confirmation and shows final scoring.

Run the automated engine, CLI, and HTTP checks with:

```powershell
python -m unittest discover -v
```

The browser highlight logic also has JavaScript checks: `node --test tests/test_ui.cjs` (Node.js is needed only for these checks, not to play).

The editable defaults are in `buraco/config.py`; both interfaces also offer them during setup. The shared rules are in `buraco/engine.py`, the CLI in `buraco/cli.py`, and the browser server and assets in `buraco/web.py` and `buraco/static/`.

## Purpose

Implement a local, turn-based Python command-line program for Windows for one complete hand of **Buraco Aberto**. Four human players share the terminal; the program enforces the rules, tracks score for the hand, and shows the active player's private hand plus every public game state. The single-page in-browser GUI uses the same rules engine.

## Fixed game format

- Four players, in two partnerships: `Team 1` (players 1 and 3) and `Team 2` (players 2 and 4).
- Two standard decks. By default jokers are excluded; `USE_JOKERS` optionally adds them.
- Each player is dealt 11 cards. Two 11-card *mortos* are set aside. The remainder is the stock; one card begins the face-up discard pile.
- Each team may take only one morto. A player takes the first available morto; mortos are not assigned to teams.
- A turn is: take from stock **or the entire open discard pile**, optionally meld/add cards, then discard exactly one card, unless a legal go-out ends the hand first. Taking the discard pile has no immediate-meld requirement.
- A player who empties their hand by melding immediately takes a morto if their team has not taken one and one is available, and may continue playing during that turn until discarding or legally going out. Emptying the hand by discarding also grants an available morto, but ends the turn; the player must wait until their next turn to play it.
- A player may go out by melding all remaining cards and/or by making a final discard of any card, including a two or joker. A team must have taken its morto, unless no morto remains available, and must own a clean canastra when `REQUIRE_CLEAN_CANASTRA_TO_GO_OUT` is enabled. Reject an entire move that empties the hand when neither taking a morto nor going out is permitted.
- Drawing the last stock card does not immediately convert a morto into stock. The player completes their turn and may claim an available morto. At turn end, if stock is empty, shuffle the first remaining available morto into a new stock, regardless of whether another morto has been taken. If none remains, end and score the hand; no further discard-pile turns occur.
- End and score the hand after `NO_PROGRESS_TURN_LIMIT` consecutive completed turns without drawing from stock, laying down or adding cards, or taking a morto. Any such action resets the counter; taking the discard pile alone does not. The default limit is 12 turns.

## Legal melds

- A run is three or more ascending cards of one suit. Aces may be low or high, and a run may span `A–2–3–…–Q–K–A` using both ace copies. No other wrapping is allowed: `K–A–2` (or `2–A–K`) is invalid. A wild may fill a missing rank, including in an ace-high run.
- An ace set contains at least three cards: three natural aces, or two natural aces and one wild. It may contain any or all eight natural aces, including duplicate suits.
- Each meld, whether a run or ace set, may contain at most one card used as a wild. Together with the minimum meld length, this ensures at least two natural cards.
- A `2` may be used as a wild card; a suited `2` in its natural run position is natural instead. An extra suited two may be wild while another occupies the natural position. A joker, if enabled, is always wild.
- Prefer an arrangement using the two naturally whenever possible. Revalidate and rearrange the whole meld when cards are added: wild positions are not locked, and a suited two may become natural. For example, adding `6h` to `2h 3h 4h` is legal because the two can represent `5h`.
- Players may only extend existing melds and rearrange cards within that same meld. They may not remove cards, split melds, or combine melds. A partnership may have multiple runs of the same suit and multiple ace sets.
- A meld with seven or more cards is a *canastra*. A canastra with no cards used as wilds is clean; otherwise it is dirty. Clean/dirty labels apply only to canastras. Adding cards may turn a dirty canastra into a clean one.

## Vulnerability and scoring

- `VULNERABILITY_THRESHOLD = 1500` and `VULNERABILITY_MINIMUM_MELD = 75` are configurable defaults.
- Determine each team's vulnerability from its prior score at hand start; vulnerability does not change during the hand. A team at or above the threshold must make its first meld play total at least the minimum card-point value. Multiple new melds may be submitted together in that one play using `|`.
- Card values: ace = 15; 2, joker, and 8 through king = 10; 3 through 7 = 5.
- All cards in table melds score their individual values, in addition to canastra bonuses. Clean canastra = +200; dirty canastra = +100; going out = +100; a team that never took a morto = −100, including when its morto became stock; cards remaining in a team's hands are negative. For example, a clean `2–3–4–5–6–7–8` scores 245 points.
- `ALLOW_A_TO_K_CLEAN_CANASTRA` and `ALLOW_A_TO_A_CLEAN_CANASTRA` enable the special +500 and +1,000 bonuses respectively. Both are disabled by default, so their special bonus contribution is zero and ordinary canastra scoring applies. When enabled, the applicable special bonus replaces the +200 clean-canastra bonus rather than adding to it.
- The program plays and scores one hand only. Cumulative match scoring is out of scope, though the engine accepts prior team scores for vulnerability. Equal final hand scores produce a draw.

## Configuration and startup

Source-level defaults:

```python
USE_JOKERS = False
REQUIRE_CLEAN_CANASTRA_TO_GO_OUT = True
VULNERABILITY_THRESHOLD = 1500
VULNERABILITY_MINIMUM_MELD = 75
ALLOW_A_TO_K_CLEAN_CANASTRA = False
ALLOW_A_TO_A_CLEAN_CANASTRA = False
NO_PROGRESS_TURN_LIMIT = 12
```

After startup, prompt for game options using these defaults, both teams' prior scores, and an optional random seed for reproducible deals. A blank seed produces a random deal. Once setup is complete, `start` begins the hand. Saving and resuming are out of scope.

## Terminal display

At the beginning of each player's turn, clear or visually separate the prior turn and show:

1. Active player and team.
2. That player's numbered, sorted hand.
3. Stock count and full discard pile, with top clearly marked.
4. Team 1's melds and Team 2's melds separately, including canastra status and clean/dirty labels for canastras.
5. Each morto's state: available, taken by a team, or moved to stock.
6. Vulnerability state and the active team's current hand score.

Only the active player's hand is displayed; all table information is public. Live scores show public table points; hand and morto penalties are shown at hand end so hidden-hand point totals are not revealed during play. Do not require a “press Enter when ready” handoff prompt.

## Command interface

Commands use case-insensitive card selectors such as `3s`, `10h`, `ad`, and `Jok` for a joker. Repeat a selector to choose both copies when necessary. Automatically select either matching copy; identical copies are interchangeable for play.

```text
start
draw stock
take discard
meld <card> <card> <card> [...] [| <card> <card> <card> [...]]
add <card> [...] to <meld-id>
discard <card>
show
help
quit
```

- `start` begins the hand after setup.
- `draw stock` or `take discard` is required exactly once per turn before melding, adding cards, or discarding.
- `meld` creates one or more valid new partnership melds; `|` separates melds that must be laid down together. A vulnerable team's opening meld play must meet the minimum as a whole; it cannot build toward the minimum with separate commands.
- `add` extends one existing partnership meld with one or more cards after the opening requirement is met. Each command has exactly one target meld.
- `discard` removes exactly one card, ends the turn, and advances clockwise unless the hand ends.
- `show` redraws state and `help` lists syntax; neither alters the turn.
- `quit` exits only after confirmation; if a hand is in progress, calculate and display scores for table melds and remaining hands, with applicable bonuses and penalties, before exiting. There is no rule-bypass command.

## Engine model and validation

- `Card`: immutable identity, rank, suit, optional joker flag.
- `Meld`: type (`run` or `ace_set`), ordered cards, wild-card positions, and derived canastra/clean/dirty/bonus properties.
- `TeamState`: players, melds, morto state, prior score, and whether its vulnerable opening requirement has been met.
- `GameState`: stock, discard pile, two mortos, four hands, teams, active player, turn phase, consecutive no-progress turn count, and end/scoring state.
- Every state-changing command is transactional: validate first, then mutate.
- Invalid commands leave state unchanged and provide a concise explanation.
- The deck is conserved: every card exists in exactly one location.

## Acceptance checks

- Deal and display a reproducible hand when a seed is supplied.
- Reject illegal draws, malformed runs/ace sets, invalid extensions, and melding, adding, or discarding before a draw or discard pickup.
- Enforce the one-wild limit and allow rearrangement when extending a meld, including cleaning a dirty canastra.
- Allow taking and continuing to play from a morto in the same turn when obtained by melding; end the turn when obtained by discarding.
- Enforce one morto per team and replenish stock from the first available morto at turn end, allowing the last-stock-card player to claim it first.
- End after the final stock turn when no morto is available, or after 12 consecutive no-progress turns with the default configuration.
- Enforce vulnerability minimums and go-out requirements, including the exception when no morto remains available.
- At hand end or confirmed quit, show a complete scoring breakdown and winner or draw.
