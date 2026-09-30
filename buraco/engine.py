"""Transactional, interface-independent rules engine for one hand."""

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import random
import re

from .config import Rules

RANKS = {1: "A", 11: "J", 12: "Q", 13: "K"}
SUITS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
HELP = """draw stock                     Draw one card from stock.
take discard                   Take the entire discard pile.
meld 3h 4h 5h | 8s 9s 10s      Create one or more melds together.
add 6h 7h to 1                  Add cards to one of your team's melds.
discard ad                     Discard one card and end your turn.
show                           Show your hand and the table.
help                           Show commands.
quit                           Confirm, score the hand, and exit.
Selectors ignore case. Use Jok for a joker. Repeat selectors for duplicates.
Draw or take the discard pile before playing. Meld IDs are shown on the table."""


class RuleError(ValueError):
    """An invalid command; the original game remains unchanged."""


@dataclass(frozen=True)
class Card:
    id: int
    rank: int
    suit: str

    @property
    def joker(self):
        return self.rank == 0

    @property
    def selector(self):
        return "Jok" if self.joker else f"{RANKS.get(self.rank, self.rank)}{self.suit}"

    @property
    def label(self):
        return "Jok" if self.joker else f"{RANKS.get(self.rank, self.rank)}{SUITS[self.suit]}"

    @property
    def points(self):
        return 15 if self.rank == 1 else 5 if 3 <= self.rank <= 7 else 10

    def view(self):
        return {"id": self.id, "rank": RANKS.get(self.rank, str(self.rank)),
                "suit": self.suit, "symbol": SUITS.get(self.suit, "★"),
                "selector": self.selector, "label": self.label, "points": self.points}


def make_deck(use_jokers=False):
    specs = [(rank, suit) for _ in range(2) for suit in SUITS for rank in range(1, 14)]
    if use_jokers:
        specs.extend([(0, "")] * 4)
    return [Card(i, rank, suit) for i, (rank, suit) in enumerate(specs)]


def sorted_hand(cards):
    return sorted(cards, key=lambda c: (list(SUITS).index(c.suit) if c.suit else 4, c.rank, c.id))


@dataclass
class Meld:
    id: int
    kind: str
    cards: list[Card]
    wild_id: int | None = None
    start: int | None = None

    @property
    def canastra(self):
        return len(self.cards) >= 7

    @property
    def status(self):
        if not self.canastra:
            return "Meld"
        return "Clean canastra" if self.wild_id is None else "Dirty canastra"

    def bonus(self, rules):
        if not self.canastra:
            return 0
        if self.wild_id is not None:
            return 100
        if self.kind == "run":
            if len(self.cards) == 14 and rules.allow_a_to_a_clean_canastra:
                return 1000
            if len(self.cards) == 13 and rules.allow_a_to_k_clean_canastra:
                return 500
        return 200

    def view(self, rules):
        cards = []
        for i, card in enumerate(self.cards):
            item = card.view()
            item["wild"] = card.id == self.wild_id
            if item["wild"]:
                rank = self.start + i if self.kind == "run" else 1
                item["represents"] = RANKS.get(1 if rank == 14 else rank, str(rank))
            cards.append(item)
        return {"id": self.id, "kind": self.kind, "cards": cards,
                "status": self.status, "canastra": self.canastra,
                "bonus": self.bonus(rules), "card_points": sum(c.points for c in self.cards)}


def validate_meld(cards, meld_id=0, kind=None):
    """Try all nonwrapping intervals, with at most one designated wild.

    Position 14 is a high ace, so the single 1..14 interval also permits A..A.
    Trying no wild first prefers a natural two, without locking that choice.
    """
    if len(cards) < 3:
        raise RuleError("A meld needs at least three cards.")
    if len({c.id for c in cards}) != len(cards):
        raise RuleError("The same physical card cannot be used twice.")
    wild_candidates = [None] + [c for c in cards if c.rank in (0, 2)]
    if kind in (None, "ace_set"):
        for wild in wild_candidates:
            natural = [c for c in cards if c != wild]
            if len(natural) >= 2 and all(c.rank == 1 for c in natural):
                return Meld(meld_id, "ace_set", sorted_hand(natural) + ([wild] if wild else []),
                            wild.id if wild else None)
    if kind in (None, "run") and len(cards) <= 14:
        for wild in wild_candidates:
            natural = [c for c in cards if c != wild]
            if any(c.joker for c in natural) or len({c.suit for c in natural}) != 1:
                continue
            for start in range(1, 16 - len(cards)):
                unused = list(natural)
                ordered = []
                wild_used = False
                for position in range(start, start + len(cards)):
                    rank = 1 if position == 14 else position
                    card = next((c for c in unused if c.rank == rank), None)
                    if card:
                        unused.remove(card)
                        ordered.append(card)
                    elif wild and not wild_used:
                        ordered.append(wild)
                        wild_used = True
                    else:
                        break
                if len(ordered) == len(cards) and not unused:
                    return Meld(meld_id, "run", ordered, wild.id if wild else None, start)
    raise RuleError("Use a same-suit run or an ace set, with at most one wild and no duplicate run ranks (except A–…–A).")


@dataclass
class TeamState:
    prior_score: int = 0
    melds: list[Meld] = field(default_factory=list)
    took_morto: bool = False
    opened: bool = False


class Game:
    def __init__(self, rules=None, prior_scores=(0, 0), seed=None):
        self.rules = rules or Rules()
        if len(prior_scores) != 2 or any(type(v) is not int for v in prior_scores):
            raise ValueError("Supply two integer prior scores.")
        self.rng = random.Random(seed)
        self.deck = make_deck(self.rules.use_jokers)
        self.stock = list(self.deck)
        self.rng.shuffle(self.stock)
        self.hands = [[] for _ in range(4)]
        for _ in range(11):
            for hand in self.hands:
                hand.append(self.stock.pop())
        self.mortos = [[self.stock.pop() for _ in range(11)] for _ in range(2)]
        self.morto_states = ["available", "available"]
        self.discard = [self.stock.pop()]
        self.teams = [TeamState(score) for score in prior_scores]
        self.active = 0
        self.phase = "draw"
        self.turn = 1
        self.next_meld_id = 1
        self.no_progress = 0
        self.turn_progress = False
        self.ended = False
        self.end_reason = None
        self.went_out = None
        self.revision = 0
        self.events = ["Hand started. Player 1 draws first."]
        self.assert_conserved()

    @property
    def team_index(self):
        return self.active % 2

    @property
    def team(self):
        return self.teams[self.team_index]

    def vulnerable(self, index):
        return self.teams[index].prior_score >= self.rules.vulnerability_threshold

    def assert_conserved(self):
        locations = self.stock + self.discard
        locations += [c for hand in self.hands for c in hand]
        locations += [c for morto in self.mortos for c in morto]
        locations += [c for team in self.teams for meld in team.melds for c in meld.cards]
        if Counter(locations) != Counter(self.deck):
            raise AssertionError("Card conservation failed.")

    def _select(self, selectors):
        if not selectors:
            raise RuleError("Specify at least one card.")
        available = list(self.hands[self.active])
        selected = []
        for selector in selectors:
            card = next((c for c in available if c.selector.lower() == selector.lower()), None)
            if card is None:
                raise RuleError(f"Your hand does not contain an available '{selector}'. Use selectors such as 3s, 10h, ad, or Jok.")
            available.remove(card)
            selected.append(card)
        return selected

    def _remove(self, cards):
        for card in cards:
            self.hands[self.active].remove(card)

    def _empty_hand(self):
        if self.hands[self.active]:
            return
        available = next((i for i, state in enumerate(self.morto_states) if state == "available"), None)
        if not self.team.took_morto and available is not None:
            self.hands[self.active].extend(self.mortos[available])
            self.mortos[available] = []
            self.morto_states[available] = f"taken by Team {self.team_index + 1}"
            self.team.took_morto = True
            self.turn_progress = True
            self.events.append(f"Player {self.active + 1} took morto {available + 1}.")
            return
        if self.rules.require_clean_canastra_to_go_out and not any(
                m.canastra and m.wild_id is None for m in self.team.melds):
            raise RuleError("You need a clean canastra to go out. Keep at least one card in hand.")
        self.went_out = self.team_index
        self._finish(f"Team {self.team_index + 1} went out")

    def _finish(self, reason):
        self.ended = True
        self.phase = "ended"
        self.end_reason = reason
        self.events.append(f"Hand ended: {reason}.")

    def _end_turn(self):
        if self.ended:
            return
        self.no_progress = 0 if self.turn_progress else self.no_progress + 1
        if not self.stock:
            available = next((i for i, state in enumerate(self.morto_states) if state == "available"), None)
            if available is None:
                self._finish("Stock exhausted; no morto remains available")
                return
            self.stock = self.mortos[available]
            self.mortos[available] = []
            self.rng.shuffle(self.stock)
            self.morto_states[available] = "moved to stock"
            self.events.append(f"Morto {available + 1} replenished the stock.")
        if self.no_progress >= self.rules.no_progress_turn_limit:
            self._finish(f"No progress for {self.no_progress} consecutive turns")
            return
        self.active = (self.active + 1) % 4
        self.turn += 1
        self.phase = "draw"
        self.turn_progress = False

    def execute(self, command):
        """Only commit after syntax, rules, end transitions, and conservation pass."""
        command = command.strip()
        if command.lower() in ("show", "help"):
            return HELP if command.lower() == "help" else "Table refreshed."
        if self.ended:
            raise RuleError("This hand has ended. Start a new hand to play again.")
        if not command:
            raise RuleError("Enter a command. Type help to see the syntax.")
        candidate = deepcopy(self)
        message = candidate._apply(command)
        candidate.assert_conserved()
        candidate.revision += 1
        candidate.events = candidate.events[-12:]
        self.__dict__.update(candidate.__dict__)
        return message

    def _apply(self, command):
        tokens = command.lower().split()
        verb = tokens[0]
        if tokens in (["draw", "stock"], ["take", "discard"]):
            if self.phase != "draw":
                raise RuleError("You have already drawn or picked up this turn.")
            if verb == "draw":
                if not self.stock:
                    raise RuleError("There are no cards in stock.")
                self.hands[self.active].append(self.stock.pop())
                self.turn_progress = True
                message = f"Player {self.active + 1} drew from stock."
            else:
                if not self.discard:
                    raise RuleError("The discard pile is empty.")
                count = len(self.discard)
                self.hands[self.active].extend(self.discard)
                self.discard.clear()
                message = f"Player {self.active + 1} took {count} discard card(s)."
            self.phase = "play"
        elif verb in ("meld", "add", "discard"):
            if self.phase != "play":
                raise RuleError("Draw from stock or take the discard pile before playing cards.")
            if verb == "meld":
                groups = [group.split() for group in command[4:].lower().split("|")]
                if any(len(group) < 3 for group in groups):
                    raise RuleError("Each new meld needs at least three cards; separate complete melds with |.")
                cards = self._select([selector for group in groups for selector in group])
                if not self.team.opened and self.vulnerable(self.team_index):
                    if sum(c.points for c in cards) < self.rules.vulnerability_minimum_meld:
                        raise RuleError(f"Your opening play must contain at least {self.rules.vulnerability_minimum_meld} card points. Submit melds together with |.")
                offset = 0
                for group in groups:
                    meld = validate_meld(cards[offset:offset + len(group)], self.next_meld_id)
                    self.team.melds.append(meld)
                    self.next_meld_id += 1
                    offset += len(group)
                self.team.opened = True
                self._remove(cards)
                self.turn_progress = True
                message = f"Player {self.active + 1} laid down {len(groups)} meld(s)."
            elif verb == "add":
                match = re.fullmatch(r"add\s+(.+?)\s+to\s+(\d+)", command, re.IGNORECASE)
                if not match:
                    raise RuleError("Use: add <card> [...] to <meld-id>.")
                if not self.team.opened:
                    raise RuleError("Make your team's opening meld play first.")
                meld = next((m for m in self.team.melds if m.id == int(match[2])), None)
                if meld is None:
                    raise RuleError("Choose a meld belonging to your team.")
                cards = self._select(match[1].split())
                replacement = validate_meld(meld.cards + cards, meld.id, meld.kind)
                self.team.melds[self.team.melds.index(meld)] = replacement
                self._remove(cards)
                self.turn_progress = True
                message = f"Player {self.active + 1} added {len(cards)} card(s) to meld {meld.id}."
            else:
                if len(tokens) != 2:
                    raise RuleError("Discard exactly one card: discard <card>.")
                cards = self._select(tokens[1:])
                self._remove(cards)
                self.discard.extend(cards)
                message = f"Player {self.active + 1} discarded {cards[0].selector}."
            self.events.append(message)
            self._empty_hand()
            if verb == "discard":
                self._end_turn()
            return message
        elif tokens == ["quit"]:
            self._finish("Hand stopped by players")
            return "Hand scored."
        else:
            raise RuleError("Unknown command or invalid syntax. Type help for commands.")
        self.events.append(message)
        return message

    def scores(self, final=True):
        result = []
        for index, team in enumerate(self.teams):
            components = {
                "table_cards": sum(c.points for m in team.melds for c in m.cards),
                "canastra_bonuses": sum(m.bonus(self.rules) for m in team.melds),
                "going_out": 100 if self.went_out == index else 0,
                "morto_penalty": -100 if final and not team.took_morto else 0,
                "hand_penalty": -sum(c.points for player in (index, index + 2) for c in self.hands[player]) if final else 0,
            }
            result.append({**components, "total": sum(components.values())})
        return result

    def view(self):
        # Mid-hand views must not reveal the point totals of hidden hands.
        scores = self.scores(final=self.ended)
        winner = None
        if self.ended:
            winner = "Draw" if scores[0]["total"] == scores[1]["total"] else f"Team {1 if scores[0]['total'] > scores[1]['total'] else 2} wins"
        return {
            "revision": self.revision, "active": self.active + 1, "team": self.team_index + 1,
            "turn": self.turn, "phase": self.phase, "ended": self.ended,
            "end_reason": self.end_reason, "winner": winner,
            "hand": [c.view() for c in sorted_hand(self.hands[self.active])],
            "players": [{"player": i + 1, "team": i % 2 + 1, "count": len(hand)} for i, hand in enumerate(self.hands)],
            "stock_count": len(self.stock), "discard": [c.view() for c in self.discard],
            "mortos": self.morto_states, "no_progress": self.no_progress,
            "teams": [{"number": i + 1, "prior_score": t.prior_score, "vulnerable": self.vulnerable(i),
                       "opened": t.opened, "took_morto": t.took_morto,
                       "melds": [m.view(self.rules) for m in t.melds]} for i, t in enumerate(self.teams)],
            "scores": scores, "rules": asdict(self.rules), "events": self.events,
        }
