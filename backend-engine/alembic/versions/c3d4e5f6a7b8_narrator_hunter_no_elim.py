"""narrator_hunter_no_elim

Adds 20 preset scripts each for hunter_revenge and no_elimination triggers.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_DATA = [
    # hunter_revenge — uses {eliminated_name} placeholder
    ('hunter_revenge', "Dying, the hunter raises their weapon -- {eliminated_name} falls with them!"),
    ('hunter_revenge', "A final shot! {eliminated_name} is taken down by the hunter's last act!"),
    ('hunter_revenge', "Even in death -- the hunter claims {eliminated_name}! A final, furious vengeance!"),
    ('hunter_revenge', "The hunter falls -- but not alone! {eliminated_name} joins them in the abyss!"),
    ('hunter_revenge', "Death, doesn't stop the hunter! {eliminated_name} -- catch that bullet!"),
    ('hunter_revenge', "One last breath -- one last shot! {eliminated_name}, you should have run!"),
    ('hunter_revenge', "The hunter's dying act? Dragging {eliminated_name} straight into the grave with them!"),
    ('hunter_revenge', "Eliminated, but not finished! The hunter's final bullet finds {eliminated_name}!"),
    ('hunter_revenge', "The hunter goes down -- guns blazing! {eliminated_name} pays the ultimate price!"),
    ('hunter_revenge', "Even dead hunters, have aim! {eliminated_name} -- that shot was meant, for you!"),
    ('hunter_revenge', "The hunter, breathing their last -- fires true! {eliminated_name} drops!"),
    ('hunter_revenge', "A parting gift from the hunter -- {eliminated_name}, your invitation to the afterlife has arrived!"),
    ('hunter_revenge', "Revenge, from beyond the grave! The hunter takes {eliminated_name} along for the ride!"),
    ('hunter_revenge', "The hunter laughs last! {eliminated_name} -- that final bullet had your name on it!"),
    ('hunter_revenge', "Die? Sure -- but not before taking {eliminated_name} down! The hunter's aim holds true!"),
    ('hunter_revenge', "The hunter, slumping -- fires one final, perfect shot! {eliminated_name} is no more!"),
    ('hunter_revenge', "With their dying breath, the hunter screams -- and {eliminated_name} answers with their life!"),
    ('hunter_revenge', "The hunter refuses to go quietly -- {eliminated_name} learns this the hard way!"),
    ('hunter_revenge', "A final, defiant shot rings out -- {eliminated_name}, the hunter sends their regards!"),
    ('hunter_revenge', "The hunter falls -- but takes {eliminated_name} along! Death, loves company!"),

    # no_elimination — no placeholder
    ('no_elimination', "The vote is tied -- nobody escapes tonight's shadow!"),
    ('no_elimination', "Indecision grips the village. The wolves smile in the darkness..."),
    ('no_elimination', "A deadlock. The village, divided -- the wolves, delighted. Heh heh..."),
    ('no_elimination', "No one is eliminated. How... convenient, for the monsters among you."),
    ('no_elimination', "The village couldn't agree. The wolves couldn't be happier -- heh heh heh..."),
    ('no_elimination', "A tie! No blood spilled today -- but don't worry, night is coming."),
    ('no_elimination', "Indecisive to the end. The killer walks free -- for now. Heh..."),
    ('no_elimination', "The vote, produces nothing. A spectacular, collective failure. Well done."),
    ('no_elimination', "No elimination. The wolf breathes a sigh of relief -- did you notice? Heh..."),
    ('no_elimination', "The village, stumped. The predator, safe. Try harder next time, perhaps."),
    ('no_elimination', "A tied vote -- and the darkness grows hungrier. Sleep tight."),
    ('no_elimination', "No verdict. No victim. Just wolves, laughing quietly in the crowd."),
    ('no_elimination', "The village, paralyzed by indecision. The hunt continues -- for everyone."),
    ('no_elimination', "Nobody goes. The wolves stay. The village learns nothing. As usual. Heh."),
    ('no_elimination', "Deadlocked! The imposter survives another day -- patience, rewarded."),
    ('no_elimination', "No elimination today. The monster among you is still listening -- and smiling."),
    ('no_elimination', "The vote collapses. The wolves feast on your indecision -- heh heh..."),
    ('no_elimination', "Unable to decide, the village lets the wolf walk free. Again. Bravo."),
    ('no_elimination', "A stalemate. The darkness sighs -- not from defeat, but anticipation. Heh heh..."),
    ('no_elimination', "No one is chosen. No one is safe. The night approaches -- and it remembers."),
]


def upgrade() -> None:
    narrator_scripts = sa.table(
        'narrator_scripts',
        sa.column('trigger_id', sa.String),
        sa.column('text', sa.Text),
    )
    op.bulk_insert(narrator_scripts, [
        {"trigger_id": t, "text": txt} for t, txt in _SEED_DATA
    ])


def downgrade() -> None:
    op.execute(
        "DELETE FROM narrator_scripts WHERE trigger_id IN ('hunter_revenge', 'no_elimination')"
    )
