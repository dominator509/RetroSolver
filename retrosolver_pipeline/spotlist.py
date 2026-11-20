"""Spot-list format: load (JSON or CSV), validate, normalize, and render
TexasSolver console_solver command scripts.

The spot list holds solver INPUTS only (board, ranges, pot, stacks, bet sizes,
accuracy target). It never holds strategy output.

TexasSolver CLI facts this module relies on (verified against
bupticybee/TexasSolver v0.2.0 src/tools/CommandLineTool.cpp):
  * each line is split on ' ' and must have at most 2 tokens, so ranges and
    bet-size lists must not contain spaces;
  * set_pot P sets each player's commitment to P/2;
  * set_accuracy is the target exploitability in percent of the pot and has no
    default (it must always be set);
  * the v0.2.0 release binary has no set_raise_limit command (raise limit 4);
  * there is no comment syntax; unknown lines only print "command not
    recognized", so the generator emits no comments or blank lines;
  * std::getline keeps '\\r', so input files must use LF line endings.
"""
import csv
import io
import json
import math
import re

from . import SPOT_LIST_SCHEMA

RANKS = "23456789TJQKA"
SUITS = "cdhs"
STREETS = ("flop", "turn", "river")
PLAYERS = ("oop", "ip")
BET_TYPES = ("bet", "raise", "donk", "allin")
SPOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
CARD_RE = re.compile(r"^[2-9TJQKA][cdhs]$")
HAND_CLASS_RE = re.compile(r"^([2-9TJQKA])([2-9TJQKA])([so]?)$")

SOLVER_DEFAULTS = {
    "thread_num": 8,
    "max_iteration": 200,
    "print_interval": 10,
    "use_isomorphism": 1,
    "dump_rounds": 1,
    "allin_threshold": 0.67,
}
SOLVER_OUTPUT_FILE = "output_result.json"


class SpotListError(ValueError):
    pass


def _num(v, field, positive=True, allow_zero=False):
    if isinstance(v, bool):
        raise SpotListError("%s must be a number, got bool" % field)
    if isinstance(v, str):
        try:
            v = float(v.strip())
        except ValueError:
            raise SpotListError("%s must be a number, got %r" % (field, v))
    if not isinstance(v, (int, float)) or not math.isfinite(v):
        raise SpotListError("%s must be a finite number, got %r" % (field, v))
    if positive and (v < 0 or (v == 0 and not allow_zero)):
        raise SpotListError("%s must be > 0, got %r" % (field, v))
    return int(v) if float(v).is_integer() else float(v)


def _int(v, field, minimum=0):
    n = _num(v, field, positive=False)
    if not float(n).is_integer() or n < minimum:
        raise SpotListError("%s must be an integer >= %d, got %r" % (field, minimum, v))
    return int(n)


def parse_board(board, field="board"):
    if isinstance(board, list):
        cards = board
    elif isinstance(board, str):
        cards = [c for c in re.split(r"[,\s]+", board.strip()) if c]
        if len(cards) == 1 and len(cards[0]) in (6, 8, 10):  # "QsJh2h"
            s = cards[0]
            cards = [s[i:i + 2] for i in range(0, len(s), 2)]
    else:
        raise SpotListError("%s must be a string or list" % field)
    norm = []
    for c in cards:
        c = c.strip()
        c = c[0].upper() + c[1:].lower() if len(c) == 2 else c
        if not CARD_RE.match(c):
            raise SpotListError("%s: bad card %r" % (field, c))
        norm.append(c)
    if len(norm) not in (3, 4, 5):
        raise SpotListError("%s must have 3, 4 or 5 cards, got %d" % (field, len(norm)))
    if len(set(norm)) != len(norm):
        raise SpotListError("%s has duplicate cards: %s" % (field, ",".join(norm)))
    return norm


def street_of(board_cards):
    return {3: "flop", 4: "turn", 5: "river"}[len(board_cards)]


def validate_range(rng, field):
    if not isinstance(rng, str) or not rng.strip():
        raise SpotListError("%s must be a non-empty range string" % field)
    if re.search(r"\s", rng.strip()):
        raise SpotListError("%s must not contain whitespace (TexasSolver splits CLI lines on spaces)" % field)
    seen = set()
    for tok in rng.strip().split(","):
        hand, _, weight = tok.partition(":")
        m = HAND_CLASS_RE.match(hand)
        if not m:
            raise SpotListError("%s: bad hand class %r (use e.g. AA, AKs, AKo, KQ)" % (field, hand))
        r1, r2, so = m.groups()
        if r1 == r2 and so:
            raise SpotListError("%s: pair %r cannot be suited/offsuit" % (field, hand))
        if RANKS.index(r1) < RANKS.index(r2):
            raise SpotListError("%s: write the higher rank first (%r)" % (field, hand))
        if hand in seen:
            raise SpotListError("%s: duplicate hand class %r" % (field, hand))
        seen.add(hand)
        if weight != "" or tok.endswith(":"):
            try:
                w = float(weight)
            except ValueError:
                raise SpotListError("%s: bad weight in %r" % (field, tok))
            if not (0 < w <= 1):
                raise SpotListError("%s: weight must be in (0,1] in %r" % (field, tok))
    return rng.strip()


def normalize_bet_sizes(bs, streets, field="bet_sizes"):
    """bet_sizes: {street: {player: {"bet": [..], "raise": [..], "donk": [..], "allin": bool}}}"""
    if not isinstance(bs, dict) or not bs:
        raise SpotListError("%s must be a non-empty object" % field)
    out = {}
    for street, per_player in bs.items():
        if street not in STREETS:
            raise SpotListError("%s: unknown street %r" % (field, street))
        if street not in streets:
            raise SpotListError("%s: street %r is already dealt on this board" % (field, street))
        if not isinstance(per_player, dict):
            raise SpotListError("%s.%s must be an object" % (field, street))
        out[street] = {}
        for player, cfg in per_player.items():
            if player not in PLAYERS:
                raise SpotListError("%s.%s: unknown player %r" % (field, street, player))
            if not isinstance(cfg, dict):
                raise SpotListError("%s.%s.%s must be an object" % (field, street, player))
            pc = {}
            for btype, val in cfg.items():
                f = "%s.%s.%s.%s" % (field, street, player, btype)
                if btype not in BET_TYPES:
                    raise SpotListError("%s: unknown bet type" % f)
                if btype == "allin":
                    if not isinstance(val, bool):
                        raise SpotListError("%s must be true/false" % f)
                    pc["allin"] = val
                else:
                    if not isinstance(val, list):
                        raise SpotListError("%s must be a list of pot-percent sizes" % f)
                    sizes = [_num(v, f) for v in val]
                    if len(set(sizes)) != len(sizes):
                        raise SpotListError("%s has duplicate sizes" % f)
                    pc[btype] = sizes
            out[street][player] = pc
    if streets[0] not in out:
        raise SpotListError("%s must configure the spot's own street (%s)" % (field, streets[0]))
    return out


def normalize_spot(raw, defaults, idx):
    where = "spots[%d]" % idx
    if not isinstance(raw, dict):
        raise SpotListError("%s must be an object" % where)
    known = {"spot_id", "positions", "pot", "effective_stack", "board", "ranges",
             "bet_sizes", "accuracy_target", "solver_settings", "notes",
             # coverage-matrix v2 informational fields (not used by the CLI template)
             "depth_bb", "matchup_id", "texture_class"}
    extra = set(raw) - known
    if extra:
        raise SpotListError("%s: unknown fields %s" % (where, sorted(extra)))
    for req in ("spot_id", "positions", "pot", "effective_stack", "board", "ranges",
                "bet_sizes", "accuracy_target"):
        if req not in raw:
            raise SpotListError("%s: missing required field %r" % (where, req))
    sid = raw["spot_id"]
    if not isinstance(sid, str) or not SPOT_ID_RE.match(sid):
        raise SpotListError("%s: spot_id must match %s" % (where, SPOT_ID_RE.pattern))
    where = "spot %r" % sid
    pos = raw["positions"]
    if not isinstance(pos, dict) or set(pos) != {"ip", "oop"} or not all(
            isinstance(pos[k], str) and pos[k].strip() for k in pos):
        raise SpotListError("%s: positions must be {\"ip\": str, \"oop\": str}" % where)
    rng = raw["ranges"]
    if not isinstance(rng, dict) or set(rng) != {"ip", "oop"}:
        raise SpotListError("%s: ranges must be {\"ip\": str, \"oop\": str}" % where)
    board = parse_board(raw["board"], "%s board" % where)
    streets = STREETS[STREETS.index(street_of(board)):]
    settings = dict(defaults)
    ss = raw.get("solver_settings", {}) or {}
    if not isinstance(ss, dict):
        raise SpotListError("%s: solver_settings must be an object" % where)
    for k, v in ss.items():
        if k not in SOLVER_DEFAULTS:
            raise SpotListError("%s: unknown solver_settings key %r" % (where, k))
        settings[k] = v
    settings = normalize_settings(settings, where)
    spot = {
        "spot_id": sid,
        "positions": {"ip": pos["ip"].strip(), "oop": pos["oop"].strip()},
        "board": board,
        "street": streets[0],
        "pot": _num(raw["pot"], "%s pot" % where),
        "effective_stack": _num(raw["effective_stack"], "%s effective_stack" % where),
        "ranges": {"ip": validate_range(rng["ip"], "%s ranges.ip" % where),
                   "oop": validate_range(rng["oop"], "%s ranges.oop" % where)},
        "bet_sizes": normalize_bet_sizes(raw["bet_sizes"], streets, "%s bet_sizes" % where),
        "accuracy_target": _num(raw["accuracy_target"], "%s accuracy_target" % where),
        "solver_settings": settings,
    }
    if "notes" in raw:
        if not isinstance(raw["notes"], str):
            raise SpotListError("%s: notes must be a string" % where)
        spot["notes"] = raw["notes"]
    return spot


def normalize_settings(s, where):
    out = {
        "thread_num": _int(s["thread_num"], "%s thread_num" % where, 1),
        "max_iteration": _int(s["max_iteration"], "%s max_iteration" % where, 1),
        "print_interval": _int(s["print_interval"], "%s print_interval" % where, 1),
        "use_isomorphism": _int(s["use_isomorphism"], "%s use_isomorphism" % where, 0),
        "dump_rounds": _int(s["dump_rounds"], "%s dump_rounds" % where, 1),
        "allin_threshold": _num(s["allin_threshold"], "%s allin_threshold" % where),
    }
    if out["use_isomorphism"] not in (0, 1):
        raise SpotListError("%s use_isomorphism must be 0 or 1" % where)
    if out["print_interval"] > out["max_iteration"]:
        raise SpotListError("%s print_interval > max_iteration: no convergence figure would be logged" % where)
    return out


def normalize_spot_list(doc):
    if not isinstance(doc, dict):
        raise SpotListError("spot list must be a JSON object")
    if doc.get("schema") != SPOT_LIST_SCHEMA:
        raise SpotListError("schema must be %r" % SPOT_LIST_SCHEMA)
    solver = doc.get("solver")
    if not isinstance(solver, dict) or not all(
            isinstance(solver.get(k), str) and solver.get(k).strip() for k in ("name", "version")):
        raise SpotListError("solver must be {\"name\": str, \"version\": str} (the exact build Instinct runs)")
    defaults = dict(SOLVER_DEFAULTS)
    d = doc.get("defaults", {}) or {}
    if not isinstance(d, dict):
        raise SpotListError("defaults must be an object")
    for k, v in d.items():
        if k not in SOLVER_DEFAULTS:
            raise SpotListError("defaults: unknown key %r" % k)
        defaults[k] = v
    spots_raw = doc.get("spots")
    if not isinstance(spots_raw, list) or not spots_raw:
        raise SpotListError("spots must be a non-empty list")
    spots, ids = [], set()
    for i, raw in enumerate(spots_raw):
        s = normalize_spot(raw, defaults, i)
        if s["spot_id"] in ids:
            raise SpotListError("duplicate spot_id %r" % s["spot_id"])
        ids.add(s["spot_id"])
        spots.append(s)
    out = {"schema": SPOT_LIST_SCHEMA,
           "solver": {"name": solver["name"].strip(), "version": solver["version"].strip()},
           "spots": spots}
    if isinstance(doc.get("list_id"), str):
        out["list_id"] = doc["list_id"]
    return out


# ---------- CSV ----------
CSV_COLUMNS = ["spot_id", "ip_position", "oop_position", "pot", "effective_stack", "board",
               "range_ip", "range_oop", "bet_sizes", "accuracy_target"]


def parse_bet_sizes_compact(text, field):
    """'flop:oop:bet:33/75|flop:oop:allin|flop:ip:raise:60' -> nested dict."""
    out = {}
    for part in [p.strip() for p in text.split("|") if p.strip()]:
        bits = part.split(":")
        if len(bits) < 3:
            raise SpotListError("%s: bad entry %r (street:player:type[:s1/s2])" % (field, part))
        street, player, btype = bits[0], bits[1], bits[2]
        cfg = out.setdefault(street, {}).setdefault(player, {})
        if btype == "allin":
            if len(bits) != 3:
                raise SpotListError("%s: allin takes no sizes (%r)" % (field, part))
            cfg["allin"] = True
        else:
            if len(bits) != 4 or not bits[3]:
                raise SpotListError("%s: %r needs sizes" % (field, part))
            cfg[btype] = [s for s in bits[3].split("/") if s]
    return out


def spot_list_from_csv(text, solver_name, solver_version):
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise SpotListError("CSV missing columns: %s" % missing)
    spots = []
    for n, row in enumerate(reader, start=2):
        f = "CSV line %d" % n
        ss = {k: row[k] for k in SOLVER_DEFAULTS if row.get(k, "").strip()}
        spots.append({
            "spot_id": row["spot_id"].strip(),
            "positions": {"ip": row["ip_position"], "oop": row["oop_position"]},
            "pot": row["pot"], "effective_stack": row["effective_stack"],
            "board": row["board"],
            "ranges": {"ip": row["range_ip"], "oop": row["range_oop"]},
            "bet_sizes": parse_bet_sizes_compact(row["bet_sizes"], f + " bet_sizes"),
            "accuracy_target": row["accuracy_target"],
            "solver_settings": ss,
        })
    return {"schema": SPOT_LIST_SCHEMA,
            "solver": {"name": solver_name or "", "version": solver_version or ""},
            "spots": spots}


def load_spot_list(path, solver_name=None, solver_version=None):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if path.lower().endswith(".csv"):
        doc = spot_list_from_csv(text, solver_name, solver_version)
    else:
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as e:
            raise SpotListError("spot list is not valid JSON: %s" % e)
        if solver_name or solver_version:
            raise SpotListError("--solver-name/--solver-version are only for CSV input; JSON lists declare 'solver'")
    return normalize_spot_list(doc)


# ---------- TexasSolver command script ----------
def _fmt(v):
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def render_cli_script(spot):
    """Return the TexasSolver console_solver input file text (LF endings)."""
    s = spot["solver_settings"]
    lines = [
        "set_pot %s" % _fmt(spot["pot"]),
        "set_effective_stack %s" % _fmt(spot["effective_stack"]),
        "set_board %s" % ",".join(spot["board"]),
        "set_range_ip %s" % spot["ranges"]["ip"],
        "set_range_oop %s" % spot["ranges"]["oop"],
    ]
    for street in STREETS:
        for player in PLAYERS:
            cfg = spot["bet_sizes"].get(street, {}).get(player, {})
            for btype in ("bet", "raise", "donk"):
                if cfg.get(btype):
                    lines.append("set_bet_sizes %s,%s,%s,%s" % (
                        player, street, btype, ",".join(_fmt(x) for x in cfg[btype])))
            if cfg.get("allin"):
                lines.append("set_bet_sizes %s,%s,allin" % (player, street))
    lines += [
        "set_allin_threshold %s" % _fmt(s["allin_threshold"]),
        "build_tree",
        "set_thread_num %d" % s["thread_num"],
        "set_accuracy %s" % _fmt(spot["accuracy_target"]),
        "set_max_iteration %d" % s["max_iteration"],
        "set_print_interval %d" % s["print_interval"],
        "set_use_isomorphism %d" % s["use_isomorphism"],
        "set_dump_evs %d" % s.get("dump_evs", 1),
        "start_solve",
        "set_dump_rounds %d" % s["dump_rounds"],
        "dump_result %s" % SOLVER_OUTPUT_FILE,
    ]
    for ln in lines:
        if len(ln.split(" ")) > 2:
            raise SpotListError("spot %r: CLI line would have >2 tokens: %r" % (spot["spot_id"], ln))
    return "\n".join(lines) + "\n"
