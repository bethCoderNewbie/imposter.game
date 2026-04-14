"""add_narrator_scripts

Revision ID: a1b2c3d4e5f6
Revises: 04bbb7370b42
Create Date: 2026-04-13 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '04bbb7370b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_DATA = [
    # game_start
    ('game_start', 'Welcome to the village. Please sign the waiver acknowledging that your friends are lying, homicidal maniacs.'),
    ('game_start', 'Ah, a fresh batch of victims... I mean, villagers. Let the betrayal commence.'),
    ('game_start', 'Look at you all, sitting in a circle, pretending you wouldn''t sell each other out for a corn chip.'),
    ('game_start', 'The game begins! Try to remember that the person smiling at you is actively planning your funeral.'),
    ('game_start', 'Welcome. The exits are locked, the life insurance policies are finalized, and someone is very hungry.'),
    ('game_start', 'Let’s play a fun game of ''Who gets stabbed in the back first?'' My money is on the loudest one.'),
    ('game_start', 'A shadow walks among you. Statistically, it’s the person you trust the most. Have fun with that.'),
    ('game_start', 'Seven enter, considerably fewer leave. It’s like a terrible timeshare presentation.'),
    ('game_start', 'Welcome to the village of terrible life choices. You could have stayed home, but no, you wanted to be eaten.'),
    ('game_start', 'Let the paranoia take root. Nothing ruins a friendship quite like a fictional accusation of lycanthropy.'),
    ('game_start', 'Take a good look around. Half of you are painfully naive, and the rest are pathological liars.'),
    ('game_start', 'The stage is set for a tragedy. Please try to die quietly, I have a headache.'),
    ('game_start', 'I hope you’ve all made your peace with whatever deity you pray to. You’re going to need them shortly.'),
    ('game_start', 'Let’s get this over with. Some of us have actual lives to live, unlike most of you by tomorrow morning.'),
    ('game_start', 'Breathe in the fresh air while you still have functioning lungs. The game has officially started.'),
    ('game_start', 'Innocent faces hiding absolute malice. It’s like a family reunion, but with more fur.'),
    ('game_start', 'The survival rate for this village is currently hovering around zero percent. Good luck, though!'),
    ('game_start', 'Welcome to the only game where paranoid delusions are actually a valid survival strategy.'),
    ('game_start', 'Someone here is a cold-blooded killer. The rest of you are just warm-blooded appetizers.'),
    ('game_start', 'Let the gaslighting begin! Whoever manipulates the group best gets to live another day.'),
    # night_open
    ('night_open', 'Night falls. Time to close your eyes and pretend you aren’t entirely defenseless.'),
    ('night_open', 'Go to sleep. It’s much easier for the wolves to aim for the jugular when you aren’t squirming.'),
    ('night_open', 'Darkness descends. Please keep your screaming to a minimum; it upsets the local wildlife.'),
    ('night_open', 'Shut your eyes. If you feel a sudden, sharp pain in your neck, just go with it. Fighting makes the meat tough.'),
    ('night_open', 'Time for bed. May your dreams be pleasant and your inevitable demise be swift.'),
    ('night_open', 'The sun sets, and the monsters clock in for their shift. Enjoy your nap.'),
    ('night_open', 'Sleep well! Or, you know, die horribly in your pajamas. Whichever happens first.'),
    ('night_open', 'Close your eyes. Ignorance is bliss, especially when you’re about to be disemboweled.'),
    ('night_open', 'Nighttime in the village. The perfect aesthetic for a brutal, unsolved homicide.'),
    ('night_open', 'Lights out. Remember, the dark isn’t empty, it’s just full of things with very sharp teeth.'),
    ('night_open', 'Go to sleep. The adults are going to do some light maiming.'),
    ('night_open', 'Time to rest your weary heads. One of you won’t have to worry about waking up early ever again.'),
    ('night_open', 'Night falls. It’s time for the daily transition from ''living'' to ''past tense''.'),
    ('night_open', 'Close those eyes. The last thing you want to see is the disappointment on the wolf''s face when they taste you.'),
    ('night_open', 'Sleep tight. Don’t let the bedbugs bite. The wolves, however, are a completely different story.'),
    ('night_open', 'Into the dark we go. Please make sure your wills are easily accessible on your nightstands.'),
    ('night_open', 'The village goes quiet. The kind of quiet that usually precedes a lot of dramatic blood splatter.'),
    ('night_open', 'Close your eyes. Just imagine you’re going under anesthesia, but without the benefit of a medical professional.'),
    ('night_open', 'Nighttime. A lovely period of unconsciousness right before a permanent period of unconsciousness.'),
    ('night_open', 'Go to sleep. If you wake up, congratulations! You’ve successfully delayed the inevitable.'),
    # night_close
    ('night_close', 'Good morning! Please check yourself for bite marks and missing limbs.'),
    ('night_close', 'The sun is up, and surprise: someone’s internal organs are now external. Let’s investigate!'),
    ('night_close', 'Wake up, villagers. Time to play everyone’s favorite morning game: ''Whose blood is that?'''),
    ('night_close', 'Dawn breaks. It smells like dew, fresh coffee, and a distinct lack of pulse.'),
    ('night_close', 'Morning is here. One of you is noticeably less chatty today. I wonder why.'),
    ('night_close', 'Rise and shine! Unless you’re the person who got mauled to death. You can just lie there.'),
    ('night_close', 'The village wakes. Please try not to step in the crime scene on your way to breakfast.'),
    ('night_close', 'A new day! Let’s gather around the fresh corpse and pretend we know what we’re doing.'),
    ('night_close', 'Morning light reveals a terrible truth: you are all still terrible at defending yourselves.'),
    ('night_close', 'Wakey wakey. Time to fake your grief and falsely accuse your neighbors.'),
    ('night_close', 'The sun rises, revealing that the wolves have, once again, outsmarted you literal sheep.'),
    ('night_close', 'Good morning to most of you. To the deceased: my condolences on your lack of situational awareness.'),
    ('night_close', 'Dawn arrives. The body count has gone up, but on the bright side, there’s more food to go around.'),
    ('night_close', 'Wake up. Someone is dead. Let’s try to act surprised, even though this happens literally every night.'),
    ('night_close', 'Morning! Time to inspect the carnage and draw completely illogical conclusions.'),
    ('night_close', 'The sun is shining, the birds are singing, and someone’s throat has been ripped out. Lovely.'),
    ('night_close', 'Rise and shine. Let’s start the day with a healthy dose of trauma and denial.'),
    ('night_close', 'Dawn breaks. Another night survived. Let’s see who didn’t make the cut this time around.'),
    ('night_close', 'Good morning, survivors! And a very quiet morning to the person currently fertilizing the daisies.'),
    ('night_close', 'Wake up. The night has spoken, and its vocabulary consists entirely of violence.'),
    # day_open
    ('day_open', 'The floor is open. Please begin the senseless bickering and baseless finger-pointing.'),
    ('day_open', 'Time for the village meeting. Let’s see who can shout the loudest without providing any actual evidence.'),
    ('day_open', 'Accuse away. I’m sure your gut feeling is much more reliable than actual detective work.'),
    ('day_open', 'Let the witch hunt commence. Remember, logic is forbidden; we only run on pure hysteria here.'),
    ('day_open', 'Who looks guilty? Probably the person who just realized they left the stove on, but let’s hang them anyway.'),
    ('day_open', 'Time to talk. A fantastic opportunity to watch you all dig your own graves with your mouths.'),
    ('day_open', 'The village must act. Which is tragic, because your collective IQ resembles the room temperature.'),
    ('day_open', 'Please begin presenting your flawed theories. The wolves need a good laugh before tonight’s hunt.'),
    ('day_open', 'Discuss amongst yourselves. Whoever has the most aggressive hand gestures is probably lying.'),
    ('day_open', 'Time to root out the imposter. Or just bully the quiet person. That’s usually your go-to strategy.'),
    ('day_open', 'Argue! Defend yourselves! It’s like a courtroom drama, but everyone is incompetent.'),
    ('day_open', 'Let’s hear your suspicions. I’ve brought popcorn for this absolute trainwreck of a deduction.'),
    ('day_open', 'The floor is yours. Try not to falsely accuse the doctor again, it’s getting embarrassing.'),
    ('day_open', 'Speak up! The imposter is relying on your sheer stupidity to survive. Don’t let them down!'),
    ('day_open', 'Deliberate carefully. Or just flip a coin. The success rate is exactly the same.'),
    ('day_open', 'Time to find the killer. Look for the one trying not to laugh at your deduction skills.'),
    ('day_open', 'Let the paranoia-fueled debate begin. This is why humanity is doomed, by the way.'),
    ('day_open', 'Who do we trust the least? A difficult question in a room full of habitual liars.'),
    ('day_open', 'Discuss the murder. Try to sound like you actually care about the victim. It sells the performance.'),
    ('day_open', 'The floor is open. Please proceed with your daily ritual of collective self-sabotage.'),
    # vote_open
    ('vote_open', 'Time to vote. Let’s formally endorse a terrible mistake.'),
    ('vote_open', 'The ballot is open. Grab your pitchforks and let mob mentality take the wheel!'),
    ('vote_open', 'Cast your votes. It’s time to legally sanction a murder to avenge an illegal murder.'),
    ('vote_open', 'Democracy in action. Proving that ten idiots are vastly more dangerous than one intelligent wolf.'),
    ('vote_open', 'Time to point the finger. Please ensure your finger is aimed at someone you mildly dislike.'),
    ('vote_open', 'The moment of truth. Let’s see which innocent bystander gets fed to the metaphorical woodchipper.'),
    ('vote_open', 'Vote now. Remember, your hasty decision will directly lead to someone’s demise. No pressure!'),
    ('vote_open', 'Cast your ballot. It’s like voting for a politician, except the immediate death is guaranteed.'),
    ('vote_open', 'Time to execute someone. Make it count. Or don’t. We all die eventually anyway.'),
    ('vote_open', 'The voting has commenced. Let the frantic whispering and desperate eye contact begin.'),
    ('vote_open', 'Make your choice. If you’re wrong, the blood is entirely on your hands. Have a great day!'),
    ('vote_open', 'Who gets the rope today? Let’s turn this tragedy into a full-blown circus.'),
    ('vote_open', 'Time to condemn someone. I suggest closing your eyes and pointing; it’s worked for you so far.'),
    ('vote_open', 'The ballot is open. Let’s see who failed to win the village popularity contest today.'),
    ('vote_open', 'Cast your vote. Remember, the wolf is voting too, and they’re probably laughing at you.'),
    ('vote_open', 'Time to choose a scapegoat. A time-honored human tradition when faced with complete ineptitude.'),
    ('vote_open', 'Voting time. Please submit the name of the person whose vibe is slightly off today.'),
    ('vote_open', 'The polls are open. Your chance to confidently make the situation astronomically worse.'),
    ('vote_open', 'Vote carefully. Just kidding, your votes are entirely driven by panic and spite.'),
    ('vote_open', 'Let’s tally the votes. I love seeing how confidently wrong a group of people can be.'),
    # vote_elimination
    ("vote_elimination", "{eliminated_name} -- the village has spoken, and you have been cast out!"),
    ("vote_elimination", "The votes are in -- {eliminated_name} walks the path of exile!"),
    ("vote_elimination", "{eliminated_name}! -- your time in the village is over, by popular demand!"),
    ("vote_elimination", "The crowd has decided -- farewell, {eliminated_name}! Were you the wolf?"),
    ("vote_elimination", "{eliminated_name} departs -- the village gambles its fate on this choice!"),
    # player_eliminated
    ("player_eliminated", "{eliminated_name} -- was found cold at dawn! The darkness claimed another!"),
    ("player_eliminated", "The night was not kind to {eliminated_name} -- may they rest in peace!"),
    ("player_eliminated", "{eliminated_name} -- has been silenced! The village mourns, or should it?"),
    ("player_eliminated", "At dawn's light, the truth is grim -- {eliminated_name} breathes no more!"),
    ("player_eliminated", "Another soul claimed -- {eliminated_name} did not survive the night!"),
    # wolves_win
    ("wolves_win", "The wolves have won -- darkness swallows the village whole!"),
    ("wolves_win", "Resistance was futile! The imposters have consumed every last hope!"),
    ("wolves_win", "The village has fallen -- the wolves howl in triumph!"),
    ("wolves_win", "Every precaution failed -- the darkness has won! Game over!"),
    ("wolves_win", "The imposters smile as the last defender falls -- victory belongs to the wolf!"),
    # village_wins
    ("village_wins", "The last imposter is unmasked -- light returns to the village!"),
    ("village_wins", "Justice prevails! The village has rooted out every wolf!"),
    ("village_wins", "The imposters are defeated -- peace returns at last!"),
    ("village_wins", "Together, the village triumphed -- the darkness has been banished!"),
    ("village_wins", "The hunt is over -- the village stands victorious and whole!"),
]


def upgrade() -> None:
    op.create_table(
        'narrator_scripts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trigger_id', sa.String(length=32), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_narrator_scripts_trigger_id', 'narrator_scripts', ['trigger_id'])

    narrator_scripts = sa.table(
        'narrator_scripts',
        sa.column('trigger_id', sa.String),
        sa.column('text', sa.Text),
    )
    op.bulk_insert(narrator_scripts, [
        {"trigger_id": t, "text": txt} for t, txt in _SEED_DATA
    ])


def downgrade() -> None:
    op.drop_index('ix_narrator_scripts_trigger_id', table_name='narrator_scripts')
    op.drop_table('narrator_scripts')
