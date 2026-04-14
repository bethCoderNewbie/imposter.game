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
    ('game_start', "Welcome... to the village. Please, sign the waiver -- acknowledging that your friends are, lying, homicidal maniacs."),
    ('game_start', "Ah... a fresh batch of victims -- I mean, villagers. Heh heh heh... let the betrayal, commence."),
    ('game_start', "Look at you all -- sitting in a circle -- pretending! ...you wouldn't sell each other out, for a corn chip."),
    ('game_start', "The game begins! Try to remember... that the person smiling at you? ...is actively planning, your funeral."),
    ('game_start', "Welcome. The exits are locked... the life insurance policies, are finalized... and someone, is very, very hungry."),
    ('game_start', "Let's play a fun game -- of 'Who gets stabbed in the back first?' Heh. My money? ...is on the loudest one."),
    ('game_start', "A shadow, walks among you... Statistically? ...it's the person you trust, the most. Heh heh... have fun with that."),
    ('game_start', "Seven enter... considerably fewer, leave. It's like a terrible timeshare presentation. Bwahaha..."),
    ('game_start', "Welcome! ...to the village, of terrible life choices. You could have stayed home -- but no -- you wanted to be eaten."),
    ('game_start', "Let the paranoia, take root... Nothing ruins a friendship, quite like a fictional accusation, of lycanthropy. Heh..."),
    ('game_start', "Take a good look, around. Half of you, are painfully naive... and the rest? ...are pathological liars."),
    ('game_start', "The stage, is set, for a tragedy. Please try to die quietly -- I have, a headache."),
    ('game_start', "I hope you've all, made your peace... with whatever deity, you pray to. You're going to need them, shortly."),
    ('game_start', "Let's get this over with... Some of us, have actual lives to live -- unlike most of you, by tomorrow morning."),
    ('game_start', "Breathe in, the fresh air... while you still have functioning lungs. The game, has officially started."),
    ('game_start', "Innocent faces -- hiding absolute malice. It's like a family reunion... but with more, fur. Heh heh..."),
    ('game_start', "The survival rate, for this village, is currently hovering around... zero percent. Good luck, though!"),
    ('game_start', "Welcome to the only game... where paranoid delusions, are actually a valid, survival strategy."),
    ('game_start', "Someone here, is a cold-blooded killer. The rest of you? ...are just warm-blooded, appetizers. Heh."),
    ('game_start', "Let the gaslighting begin! Whoever manipulates the group best... gets to live, another day. Ha!"),
    # night_open
    ('night_open', "Ssshhh... night falls. Close your eyes... and pretend, you aren't, entirely defenseless. ... ..."),
    ('night_open', "Go to sleep... it's much easier, for the wolves, to aim for the jugular... when you, aren't squirming. Ssshhh..."),
    ('night_open', "Darkness descends... please keep your screaming, to a minimum... sssomething, is listening. ... ..."),
    ('night_open', "Shut your eyes... if you feel a sudden, sharp pain... in your neck -- just, go with it. ... fighting makes the meat, tough."),
    ('night_open', "Time for bed... may your dreams be pleasant... and your inevitable demise... be swift. Ssshhh... ... ..."),
    ('night_open', "The sun sets... and the monsters, clock in, for their shift. Enjoy your nap... heh heh..."),
    ('night_open', "Sleep well!... Or -- you know -- die horribly, in your pajamas. Whichever, happens, first. ... ..."),
    ('night_open', "Close your eyes... ignorance, is bliss -- especially, when you're about to... be disemboweled. Ssshhh..."),
    ('night_open', "Nighttime, in the village... the perfect aesthetic, for a brutal... unsolved... homicide. ... ..."),
    ('night_open', "Lights out... remember -- the dark, isn't empty... it's just full of things, with very, sharp teeth. Ssshhh..."),
    ('night_open', "Go to sleep... the adults, are going to do some, light... maiming. Heh heh heh..."),
    ('night_open', "Time to rest, your weary heads... one of you, won't have to worry, about waking up early... ever again. ... ..."),
    ('night_open', "Night falls... it's time, for the daily transition... from 'living'... to 'past tense.' ... ..."),
    ('night_open', "Close those eyes... the last thing, you want to see... is the disappointment, on the wolf's face, when they taste you. Ssshhh..."),
    ('night_open', "Sleep tight... don't let the bedbugs bite. The wolves, however... are a completely, different story. ... ..."),
    ('night_open', "Into the dark, we go... please make sure, your wills, are easily accessible, on your nightstands. Ssshhh..."),
    ('night_open', "The village, goes quiet... the kind of quiet, that usually precedes, a lot of... dramatic, blood splatter. ... ..."),
    ('night_open', "Close your eyes... just imagine, you're going under anesthesia -- but without, the benefit, of a medical professional. Ssshhh... ... ..."),
    ('night_open', "Nighttime... a lovely period, of unconsciousness... right before, a permanent period, of unconsciousness. Heh heh..."),
    ('night_open', "Go to sleep... if you wake up -- congratulations! ...You've successfully, delayed, the inevitable. Ssshhh..."),
    # night_close
    ('night_close', "Good morning! ...please check yourself, for bite marks, and missing limbs."),
    ('night_close', "The sun is up! And surprise -- someone's internal organs, are now, external. Let's investigate!"),
    ('night_close', "Wake up, villagers... time to play everyone's favorite morning game -- 'Whose blood is that?!'"),
    ('night_close', "Dawn breaks... it smells like dew, fresh coffee... and a distinct, lack of pulse."),
    ('night_close', "Morning, is here... one of you, is noticeably less chatty, today. ...I wonder, why."),
    ('night_close', "Rise and shine! ...Unless you're the person, who got mauled to death. You can just, lie there."),
    ('night_close', "The village, wakes... please try not to step, in the crime scene, on your way to breakfast."),
    ('night_close', "A new day! ...let's gather, around the fresh corpse, and pretend, we know what we're doing."),
    ('night_close', "Morning light, reveals a terrible truth -- you are all, still terrible, at defending yourselves."),
    ('night_close', "Wakey, wakey... time to fake your grief, and falsely accuse, your neighbors."),
    ('night_close', "The sun rises, revealing, that the wolves have -- once again -- outsmarted you, literal sheep."),
    ('night_close', "Good morning, to most of you... to the deceased? My condolences, on your lack, of situational awareness."),
    ('night_close', "Dawn arrives... the body count, has gone up -- but on the bright side? ...there's more food to go around."),
    ('night_close', "Wake up. Someone, is dead. Let's try to act surprised... even though this happens, literally, every night."),
    ('night_close', "Morning! Time to inspect the carnage -- and draw, completely illogical, conclusions."),
    ('night_close', "The sun is shining! The birds are singing! And someone's throat... has been ripped out. Lovely."),
    ('night_close', "Rise and shine... let's start the day, with a healthy dose of trauma, and denial."),
    ('night_close', "Dawn breaks... another night, survived. Let's see, who didn't make, the cut, this time around."),
    ('night_close', "Good morning, survivors! And a very quiet morning... to the person, currently fertilizing, the daisies."),
    ('night_close', "Wake up... the night has spoken -- and its vocabulary, consists entirely, of violence. Heh heh..."),
    # day_open
    ('day_open', "The floor, is open... please begin, the senseless bickering, and baseless, finger-pointing."),
    ('day_open', "Time for the village meeting! Let's see, who can shout the loudest, without providing, any actual evidence."),
    ('day_open', "Accuse, away. I'm sure, your gut feeling, is much more reliable, than actual... detective work. Heh."),
    ('day_open', "Let the witch hunt, commence... remember -- logic, is forbidden! We only run, on pure hysteria, here."),
    ('day_open', "Who, looks guilty? Probably the person, who just realized, they left the stove on -- but let's hang them, anyway."),
    ('day_open', "Time to talk... a fantastic opportunity, to watch you all, dig your own graves, with your mouths."),
    ('day_open', "The village, must act! Which is tragic -- because your collective IQ, resembles the room temperature."),
    ('day_open', "Please begin, presenting your flawed theories... the wolves, need a good laugh, before tonight's hunt. Heh heh..."),
    ('day_open', "Discuss amongst yourselves... whoever has, the most aggressive hand gestures, is probably, lying."),
    ('day_open', "Time to root out, the imposter... or just bully, the quiet person. That's usually, your go-to strategy."),
    ('day_open', "Argue! Defend yourselves! It's like a courtroom drama -- but everyone, is incompetent!"),
    ('day_open', "Let's hear your suspicions... I've brought popcorn, for this absolute trainwreck, of a deduction. Ha!"),
    ('day_open', "The floor, is yours... try not to falsely accuse the doctor, again -- it's getting, embarrassing."),
    ('day_open', "Speak up! The imposter, is relying on your sheer stupidity, to survive. Don't, let them down!"),
    ('day_open', "Deliberate carefully... or just flip a coin. The success rate, is exactly, the same. Heh."),
    ('day_open', "Time to find the killer... look for the one, trying not to laugh, at your deduction skills."),
    ('day_open', "Let the paranoia-fueled debate, begin... this is why humanity, is doomed, by the way."),
    ('day_open', "Who, do we trust, the least? A difficult question -- in a room, full of habitual liars."),
    ('day_open', "Discuss the murder... try to sound like you actually care, about the victim. It sells, the performance."),
    ('day_open', "The floor, is open... please proceed, with your daily ritual, of collective self-sabotage."),
    # vote_open
    ('vote_open', "Time to vote!... Let's formally endorse, a terrible mistake."),
    ('vote_open', "The ballot, is open! Grab your pitchforks -- and let mob mentality, take the wheel!"),
    ('vote_open', "Cast your votes... it's time to legally sanction a murder, to avenge, an illegal murder."),
    ('vote_open', "Democracy! ...in action. Proving, that ten idiots, are vastly more dangerous, than one intelligent wolf."),
    ('vote_open', "Time to point, the finger... please ensure your finger, is aimed at someone, you mildly dislike."),
    ('vote_open', "The moment, of truth... Let's see, which innocent bystander, gets fed, to the metaphorical woodchipper?!"),
    ('vote_open', "Vote now! Remember -- your hasty decision, will directly lead, to someone's demise. No, pressure!"),
    ('vote_open', "Cast your ballot! It's like voting for a politician -- except the immediate death, is guaranteed."),
    ('vote_open', "Time to execute, someone... make it count. Or don't. We all die, eventually, anyway."),
    ('vote_open', "The voting, has commenced! Let the frantic whispering, and desperate eye contact, begin."),
    ('vote_open', "Make your choice... if you're wrong? ...the blood, is entirely on your hands. Have a great, day!"),
    ('vote_open', "Who, gets the rope, today?! Let's turn this tragedy, into a full-blown circus!"),
    ('vote_open', "Time to condemn, someone... I suggest closing your eyes, and pointing -- it's worked, for you, so far."),
    ('vote_open', "The ballot, is open! Let's see, who failed to win, the village popularity contest, today."),
    ('vote_open', "Cast your vote! Remember -- the wolf is voting too... and they're probably, laughing at you. Heh heh..."),
    ('vote_open', "Time to choose, a scapegoat... a time-honored human tradition, when faced, with complete ineptitude."),
    ('vote_open', "Voting time!... please submit the name, of the person, whose vibe is slightly off, today."),
    ('vote_open', "The polls, are open!... Your chance, to confidently make the situation, astronomically worse."),
    ('vote_open', "Vote carefully!... Just kidding -- your votes, are entirely driven, by panic, and spite. Ha!"),
    ('vote_open', "Let's tally, the votes... I love seeing how confidently wrong, a group of people, can be. Heh heh heh..."),
    # vote_elimination
    ('vote_elimination', "{eliminated_name}... the village has spoken. They think you're a monster -- or just, annoying. Either way, get out."),
    ('vote_elimination', "Congratulations, {eliminated_name}! You've been elected, to the position, of 'Involuntary Exile.' Heh heh..."),
    ('vote_elimination', "The votes, are in... {eliminated_name} -- you're officially the village's biggest mistake, of the day."),
    ('vote_elimination', "{eliminated_name}, is banished! Don't let the village gates, hit you on the way, to your certain doom."),
    ('vote_elimination', "Well, {eliminated_name}... it seems your charming personality, wasn't enough, to save you, from a lynching."),
    ('vote_elimination', "The mob, has decided... {eliminated_name} -- please escort yourself, to the graveyard."),
    ('vote_elimination', "Farewell, {eliminated_name}! We'd say we'll miss you -- but we literally, just voted, to get rid of you."),
    ('vote_elimination', "{eliminated_name}, departs... let's hope, for your sake, they were actually a wolf. If not?... awkward."),
    ('vote_elimination', "Out you go, {eliminated_name}!... on the bright side -- you no longer have to participate, in these stupid meetings."),
    ('vote_elimination', "The village, has cast out {eliminated_name}... another brilliant display, of sheer, unadulterated guesswork."),
    ('vote_elimination', "{eliminated_name}... your time, is up. Please leave your belongings -- the survivors, will be looting them, shortly."),
    ('vote_elimination', "And {eliminated_name}, is gone... a tragic victim, of democracy, and poor social skills. Heh."),
    ('vote_elimination', "Goodbye, {eliminated_name}... you fought valiantly -- but unfortunately, your defense, was pathetic."),
    ('vote_elimination', "The crowd, wants blood -- and {eliminated_name}, is providing it. Thanks, for being a team player!"),
    ('vote_elimination', "{eliminated_name}, has been eliminated! I'm sure the real wolf, is very grateful, for your sacrifice. Ha!"),
    ('vote_elimination', "Look at you all, so proud, of eliminating {eliminated_name}... I can't wait, to see your faces, when someone still dies, tonight."),
    ('vote_elimination', "Farewell, {eliminated_name}... you were the weakest link. Goodbye."),
    ('vote_elimination', "{eliminated_name}, walks the path of exile... may the road rise, to meet you -- and the wolves out there, find you, quickly."),
    ('vote_elimination', "The village, rejects {eliminated_name}... it's like a terrible breakup -- but with more, public shaming."),
    ('vote_elimination', "{eliminated_name}, is banished!... let's quickly move on, before the guilt, sets in."),

    # player_eliminated
    ('player_eliminated', "{eliminated_name}, was found dead... apparently, reasoning with a hungry predator, doesn't work. Who knew?"),
    ('player_eliminated', "Tragic news -- {eliminated_name}, is currently, resting in pieces. Heh heh..."),
    ('player_eliminated', "{eliminated_name}, has been silenced... on the bright side? they were a terrible conversationalist, anyway."),
    ('player_eliminated', "The night, claimed {eliminated_name}... cleanup on aisle four, please."),
    ('player_eliminated', "Oh look -- another corpse... this time, it's {eliminated_name}. I'll add them, to the spreadsheet. Heh."),
    ('player_eliminated', "{eliminated_name}, didn't survive the night... I told them, to lock their door -- but did they listen? No."),
    ('player_eliminated', "We mourn, the loss of {eliminated_name}... well, some of you do. The wolf, is just, digesting. Heh heh..."),
    ('player_eliminated', "{eliminated_name}, has expired... their warranty, has officially been voided, by a set of large teeth."),
    ('player_eliminated', "Dawn breaks -- and {eliminated_name}, is noticeably less breathing, than yesterday."),
    ('player_eliminated', "Another soul, claimed... {eliminated_name}, has crossed, the rainbow bridge. Violently. Bwahaha..."),
    ('player_eliminated', "{eliminated_name}, was murdered... if anyone wants their shoes? ...speak now, before they get bloodstained."),
    ('player_eliminated', "The darkness, was not kind, to {eliminated_name}... mostly because, the darkness, had claws. Heh heh heh..."),
    ('player_eliminated', "{eliminated_name}, is dead... let's all pause, for a moment of silence. ... ... ...okay, that's enough. Back to arguing."),
    ('player_eliminated', "We have a casualty -- {eliminated_name}... they lived a mediocre life, and died a highly dramatic death."),
    ('player_eliminated', "{eliminated_name}, has been permanently unsubscribed, from living. Heh."),
    ('player_eliminated', "Looks like {eliminated_name}, lost the game of hide and seek... and their life."),
    ('player_eliminated', "{eliminated_name}, is no more... they've joined, the choir invisible. And the local food chain. Heh heh..."),
    ('player_eliminated', "The night took {eliminated_name}... frankly, I thought they'd last, at least until Thursday. Disappointing."),
    ('player_eliminated', "{eliminated_name}, is dead... please update, your emergency contact lists, accordingly."),
    ('player_eliminated', "A moment to recognize {eliminated_name} -- who bravely served, as a midnight snack. Heh heh heh..."),

    # wolves_win
    ('wolves_win', "The wolves, win! A stunning victory, for natural selection -- and a devastating blow, to your collective egos. Bwahaha!"),
    ('wolves_win', "The village, is dead... the wolves, are full. I'd call this, a perfectly balanced ecosystem. Heh heh heh..."),
    ('wolves_win', "Game over! The wolves, have devoured, everyone... truly a triumph, of brawn -- over whatever it is you guys, were using, instead of brains. Hahaha!"),
    ('wolves_win', "The imposters, win! You literally voted out, your own protection -- and handed them, the keys. Astonishing. Ha!"),
    ('wolves_win', "Darkness, wins... you're all dead. On the bright side? ...the village, will be very quiet, now. Heh heh..."),
    ('wolves_win', "The wolves, howl in triumph!... It's hard to feel bad, for the village -- when they were, this spectacularly, incompetent. Bwahaha..."),
    ('wolves_win', "Victory! Belongs to the wolf! Congratulations, on manipulating a group of people, who couldn't agree, on the color of the sky. Hahaha!"),
    ('wolves_win', "The village, has fallen... it was less of a battle -- and more of an all-you-can-eat buffet. Heh heh heh..."),
    ('wolves_win', "Every precaution, failed -- because your precautions, were terrible. The wolves, win. Good night. Ha!"),
    ('wolves_win', "The imposters, smile, as the last defender falls... you guys, really made it, entirely too easy, for them. Heh heh..."),
    ('wolves_win', "The wolves, take the crown! The villagers, take a permanent dirt nap. Perfectly, balanced. Bwahaha!"),
    ('wolves_win', "Game over! The bad guys, won. Welcome, to the real world, folks. Heh heh heh..."),
    ('wolves_win', "The wolves, are victorious! I hope you're all happy, with your terrible choices, from the afterlife. Ha!"),
    ('wolves_win', "The village, has been, entirely consumed... I'll send a postcard, to your next of kin. Wait -- they're dead too. Hahaha!"),
    ('wolves_win', "Wolves, win! You put up a fight -- but unfortunately, your weapons, were made, of sheer stupidity. Heh heh..."),
    ('wolves_win', "The imposters, stand over the ruins... it's amazing what a little teamwork -- and pathological lying -- can achieve. Bwahaha!"),
    ('wolves_win', "Darkness, swallows the village whole... honestly, the real tragedy, is how long it took them, to finish you off. Heh heh heh..."),
    ('wolves_win', "The wolves, have won! Let this be a lesson -- never trust anyone, especially, yourselves. Ha!"),
    ('wolves_win', "The village, is wiped out... at least you don't have to play, this agonizing game, anymore. Heh heh..."),
    ('wolves_win', "Wolves, win! Flawless victory! Villagers -- please proceed, to the nearest, existential crisis. Bwahaha!"),

    # village_wins
    ('village_wins', "The village, wins!? An absolute, statistical anomaly. I demand, a recount. Heh..."),
    ('village_wins', "The last imposter, is dead! You survived! Mostly through dumb luck -- but a win, is a win, I suppose."),
    ('village_wins', "Justice, prevails! You only had to murder, several innocent people, to find the guilty one. How heroic."),
    ('village_wins', "The wolves, are defeated!... the village, is safe. Now you can go back, to dying of dysentery, like normal peasants."),
    ('village_wins', "Together! ...the village, triumphed. It's amazing, what you can accomplish -- when you stop, actively sabotaging each other."),
    ('village_wins', "The hunt, is over! You won! Please don't let this temporary success, go to your incredibly, dense heads."),
    ('village_wins', "The village, stands victorious!... I'm honestly shocked. I had already, written your eulogies. Ha!"),
    ('village_wins', "The imposters, are gone! Peace, returns... I give it three days, before you start a civil war, over a fence dispute."),
    ('village_wins', "Light returns, to the village! The nightmare, is over!... unfortunately, you still have to live, with each other."),
    ('village_wins', "The village, wins! Congratulations, on achieving the absolute bare minimum, requirement, of survival."),
    ('village_wins', "The wolves, have been, rooted out! You did it!... I'll go cancel, the mass grave excavation."),
    ('village_wins', "Victory, for the village! Enjoy the PTSD, survivors! Heh heh..."),
    ('village_wins', "The imposters, are vanquished! Let's celebrate -- by pretending, we didn't casually betray each other, yesterday."),
    ('village_wins', "The village, is safe! You managed, to kill the monsters, before they finished, their appetizers. Well done."),
    ('village_wins', "Peace, returns at last!... now you can return, to your mundane, miserable little lives. Ha!"),
    ('village_wins', "The last wolf, is gone! You won the game -- but at what cost, to your morality?! Just kidding -- you have none. Heh."),
    ('village_wins', "The village, survives! A truly disappointing day, for nihilists, everywhere. Heh heh..."),
    ('village_wins', "You did it!... the wolves, are dead. Feel free, to pat yourselves on the back, with your bloodstained hands."),
    ('village_wins', "The darkness, has been banished! Wow -- you guys, actually coordinated a thought. I'm impressed. Ha!"),
    ('village_wins', "The village, wins! Drinks are on the house!... mostly because, the bartender is dead -- and we can just take them. Hahaha!"),
    ('village_wins', "The hunt, is over -- the village, stands victorious... and whole! Heh heh..."),
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
