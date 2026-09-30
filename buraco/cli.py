"""Interactive terminal frontend."""

from dataclasses import asdict

from .config import Rules
from .engine import Game, HELP, RuleError


LABELS = {
    "use_jokers": "Include jokers",
    "require_clean_canastra_to_go_out": "Require a clean canastra to go out",
    "vulnerability_threshold": "Vulnerability threshold",
    "vulnerability_minimum_meld": "Vulnerable opening minimum",
    "allow_a_to_k_clean_canastra": "Enable 500-point A-to-K bonus",
    "allow_a_to_a_clean_canastra": "Enable 1,000-point A-to-A bonus",
    "no_progress_turn_limit": "Consecutive turns without progress before ending",
}


def ask(label, default, boolean=False, minimum=None):
    while True:
        hint = ("yes" if default else "no") if boolean else str(default)
        value = input(f"{label} [{hint}]: ").strip()
        if not value:
            return default
        if boolean:
            if value.lower() in ("y", "yes", "n", "no"):
                return value.lower() in ("y", "yes")
            print("Please enter yes or no.")
        else:
            try:
                result = int(value)
                if minimum is not None and result < minimum:
                    raise ValueError
                return result
            except ValueError:
                print(f"Please enter an integer{' at least ' + str(minimum) if minimum is not None else ''}.")


def setup():
    print("BURACO / One hand, four players\nTeam 1: players 1 + 3   Team 2: players 2 + 4\n")
    values = {}
    for name, default in asdict(Rules()).items():
        values[name] = ask(LABELS[name], default, type(default) is bool,
                           1 if name == "no_progress_turn_limit" else 0)
    scores = [ask(f"Team {i} prior score", 0) for i in (1, 2)]
    seed = input("Optional random seed [blank for random]: ").strip() or None
    while True:
        command = input("Setup complete. Type start to deal, or quit: ").strip().lower()
        if command == "start":
            return Game(Rules(**values), scores, seed)
        if command == "quit" and ask("Quit", False, True):
            return None
        print("Type start to begin or quit to exit.")


def score_text(state):
    lines = []
    names = [("table_cards", "Table cards"), ("canastra_bonuses", "Canastras"),
             ("going_out", "Going out"), ("morto_penalty", "Morto penalty"),
             ("hand_penalty", "Cards in hand"), ("total", "TOTAL")]
    lines.append(f"{'Hand score':<20} {'Team 1':>10} {'Team 2':>10}")
    for key, label in names:
        if not state["ended"] and key in ("morto_penalty", "hand_penalty"):
            lines.append(f"{label:<20} {'pending':>10} {'pending':>10}")
        else:
            lines.append(f"{label:<20} {state['scores'][0][key]:>10} {state['scores'][1][key]:>10}")
    return "\n".join(lines)


def display(game):
    state = game.view()
    print("\n" + "=" * 76)
    print(f"TURN {state['turn']} / PLAYER {state['active']} / TEAM {state['team']} / {state['phase'].upper()}")
    print("Your hand: " + "  ".join(f"{i}:{c['selector']}" for i, c in enumerate(state["hand"], 1)))
    print(f"Stock: {state['stock_count']} cards")
    print("Discard (bottom -> TOP): " + (" ".join(c["selector"] for c in state["discard"]) or "empty"))
    for team in state["teams"]:
        vulnerability = ("vulnerable, opening met" if team["opened"] else f"vulnerable, needs {game.rules.vulnerability_minimum_meld} points to open") if team["vulnerable"] else "not vulnerable"
        print(f"\nTeam {team['number']} / {vulnerability} / prior score {team['prior_score']}")
        if not team["melds"]:
            print("  No melds yet.")
        for meld in team["melds"]:
            cards = " ".join(c["selector"] + (f"(as {c['represents']})" if c["wild"] else "") for c in meld["cards"])
            print(f"  #{meld['id']} {cards} / {meld['status']} / cards {meld['card_points']} + bonus {meld['bonus']}")
    print("\n" + " | ".join(f"Morto {i}: {status}" for i, status in enumerate(state["mortos"], 1)))
    print(f"No-progress turns: {state['no_progress']}/{game.rules.no_progress_turn_limit}")
    print("\n" + ("Final scoring" if state["ended"] else "Points on the table (hand and morto penalties applied at hand end)"))
    print(score_text(state))
    if state["ended"]:
        print(f"\n{state['end_reason']}. {state['winner']}.")
    else:
        print("\nDraw or take discard." if state["phase"] == "draw" else "Meld, add, or discard.")


def main():
    game = None
    try:
        game = setup()
        if game is None:
            return
        print("\n" + HELP)
        display(game)
        while not game.ended:
            command = input(f"P{game.active + 1}> ").strip()
            if command.lower() == "quit" and not ask("Score this hand and quit", False, True):
                continue
            try:
                message = game.execute(command)
                print(message)
                if command.lower() != "help":
                    display(game)
            except RuleError as error:
                print(f"Invalid move: {error}")
    except (EOFError, KeyboardInterrupt):
        print("\nInput closed.")
        if game is not None and not game.ended:
            game.execute("quit")
            display(game)


if __name__ == "__main__":
    main()
