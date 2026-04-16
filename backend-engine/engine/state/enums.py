from enum import StrEnum


class Phase(StrEnum):
    LOBBY = "lobby"
    ROLE_DEAL = "role_deal"
    NIGHT = "night"
    DAY = "day"
    DAY_VOTE = "day_vote"
    HUNTER_PENDING = "hunter_pending"
    GAME_OVER = "game_over"


class Team(StrEnum):
    VILLAGE = "village"
    WEREWOLF = "werewolf"
    NEUTRAL = "neutral"


class InvestigationResult(StrEnum):
    VILLAGE = "village"
    WOLF = "wolf"
    NEUTRAL = "neutral"


class ActionPhase(StrEnum):
    NONE = "none"
    NIGHT = "night"
    NIGHT_ONE_ONLY = "night_one_only"
    DAY = "day"
    ON_DEATH = "on_death"


class ActionType(StrEnum):
    NONE = "none"
    INSPECT = "inspect"
    PROTECT = "protect"
    ELIMINATE_GROUP = "eliminate_group"
    ELIMINATE_SOLO = "eliminate_solo"
    ROLEBLOCK = "roleblock"
    DOUBLE_VOTE = "double_vote"
    REVENGE_KILL = "revenge_kill"
    MANIPULATE = "manipulate"
    CONVERT = "convert"
    LINK_PLAYERS = "link_players"
    MULTI_CHOICE = "multi_choice"
    TRACK = "track"
    HEAL_OR_KILL = "heal_or_kill"
    REDIRECT_KILL = "redirect_kill"


class EliminationCause(StrEnum):
    WOLF_KILL = "wolf_kill"
    VILLAGE_VOTE = "village_vote"
    ARSONIST_IGNITE = "arsonist_ignite"
    SERIAL_KILLER = "serial_killer_kill"
    BROKEN_HEART = "broken_heart"
    HUNTER_REVENGE = "hunter_revenge"
    WITCH_KILL = "witch_kill"
    LUNATIC_SACRIFICE = "lunatic_sacrifice"
    LUNATIC_CURSE = "lunatic_curse"
    BODYGUARD_KILL = "bodyguard_kill"
    BODYGUARD_SACRIFICE = "bodyguard_sacrifice"
    GRID_CHARGE_KILL = "grid_charge_kill"  # wolf pack charged a quadrant for 5 s and hit an active solver


class WinCondition(StrEnum):
    VILLAGE_WINS = "village_wins"
    WEREWOLF_WINS = "werewolf_wins"
    JESTER_WINS = "jester_wins"
    SERIAL_KILLER_WINS = "serial_killer_wins"
    ARSONIST_WINS = "arsonist_wins"


class DifficultyLevel(StrEnum):
    EASY     = "easy"
    STANDARD = "standard"
    HARD     = "hard"
