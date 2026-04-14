"""reseed_narrator_scripts

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-14

Re-seeds narrator_scripts. The bulk_insert in a1b2c3d4e5f6 was added to the
migration file after it was already stamped on running DBs, leaving the table
empty. This migration clears and repopulates the seed rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_DATA = [
    # game_start
    ('game_start', "Welcome to the village. Please, sign the waiver , acknowledging that your friends are, lying, homicidal maniacs."),  # _00
    ('game_start', "Ah a fresh batch of victims , I mean, villagers. Heh heh heh let the betrayal, commence."),  # _01
    ('game_start', "Look at you all , sitting in a circle , pretending! you wouldn't sell each other out, for a corn chip."),  # _02
    ('game_start', "The game begins! Try to remember that the person smiling at you? is actively planning, your funeral."),  # _03
    ('game_start', "Welcome. The exits are locked the life insurance policies, are finalized and someone, is very, very hungry."),  # _04
    ('game_start', "Let's play a fun game , of 'Who gets stabbed in the back first?' Heh. My money? is on the loudest one."),  # _05
    ('game_start', "A shadow, walks among you Statistically? it's the person you trust, the most. Heh heh have fun with that."),  # _06
    ('game_start', "Seven enter considerably fewer, leave. It's like a terrible timeshare presentation. Bwahaha"),  # _07
    ('game_start', "Welcome! to the village, of terrible life choices. You could have stayed home , but no , you wanted to be eaten."),  # _08
    ('game_start', "Let the paranoia, take root Nothing ruins a friendship, quite like a fictional accusation, of lycanthropy. Heh"),  # _09
    ('game_start', "Take a good look, around. Half of you, are painfully naive and the rest? are pathological liars."),  # _10
    ('game_start', "The stage, is set, for a tragedy. Please try to die quietly , I have, a headache."),  # _11
    ('game_start', "I hope you've all, made your peace with whatever deity, you pray to. You're going to need them, shortly."),  # _12
    ('game_start', "Let's get this over with Some of us, have actual lives to live , unlike most of you, by tomorrow morning."),  # _13
    ('game_start', "Breathe in, the fresh air while you still have functioning lungs. The game, has officially started."),  # _14
    ('game_start', "Innocent faces , hiding absolute malice. It's like a family reunion but with more, fur. Heh heh"),  # _15
    ('game_start', "The survival rate, for this village, is currently hovering around zero percent. Good luck, though!"),  # _16
    ('game_start', "Welcome to the only game where paranoid delusions, are actually a valid, survival strategy."),  # _17
    ('game_start', "Someone here, is a cold-blooded killer. The rest of you? are just warm-blooded, appetizers. Heh."),  # _18
    ('game_start', "Let the gaslighting begin! Whoever manipulates the group best gets to live, another day. Ha!"),  # _19
    ('game_start', "Welcome to the only place where 'trust exercises' usually end in a shallow grave. Heh heh let's begin."),  # _20
    ('game_start', "Ah, I see you've all arrived with your dignity intact. Don't worry, we'll strip that away by round three."),  # _21
    ('game_start', "Look at those innocent faces it's a shame half of them are about to become statistics. Heh. Welcome to the village."),  # _22
    ('game_start', "The game begins! Remember, if you feel like everyone is out to get you you're probably right. Have fun!"),  # _23
    ('game_start', "Welcome to the ultimate test of friendship. Or as I like to call it: 'The Great Betrayal Olympics.' May the worst person win."),  # _24
    ('game_start', "Breathe in that fresh village air it’s the last time it won’t smell like panic and bad intentions."),  # _25
    ('game_start', "The sun is setting on your trust in one another. By morning, you'll be looking at your best friend and wondering where they hide the fur. Heh heh"),  # _26
    ('game_start', "I've seen many groups sit where you are. Most of them are now part of the local landscape. Let's see if you're any different."),  # _27
    ('game_start', "Welcome to the village of 'Who Stays and Who Slays.' Spoiler alert: most of you aren't staying. Bwahaha"),  # _28
    ('game_start', "Ready to play? Just remember, the only thing thicker than the tension in this room is the wolf's appetite."),  # _29
    ('game_start', "The survival rate here is lower than a submarine with screen doors. But hey, at least you're having fun, right?"),  # _30
    ('game_start', "I'm not saying you're doomed but I've already started the paperwork for the mass burial. Just being efficient."),  # _31
    # night_open
    ('night_open', "Ssshhh night falls. Close your eyes and pretend, you aren't, entirely defenseless.  "),  # _00
    ('night_open', "Go to sleep it's much easier, for the wolves, to aim for the jugular when you, aren't squirming. Ssshhh"),  # _01
    ('night_open', "Darkness descends please keep your screaming, to a minimum sssomething, is listening.  "),  # _02
    ('night_open', "Shut your eyes if you feel a sudden, sharp pain in your neck , just, go with it.  fighting makes the meat, tough."),  # _03
    ('night_open', "Time for bed may your dreams be pleasant and your inevitable demise be swift. Ssshhh  "),  # _04
    ('night_open', "The sun sets and the monsters, clock in, for their shift. Enjoy your nap heh heh"),  # _05
    ('night_open', "Sleep well! Or , you know , die horribly, in your pajamas. Whichever, happens, first.  "),  # _06
    ('night_open', "Close your eyes ignorance, is bliss , especially, when you're about to be disemboweled. Ssshhh"),  # _07
    ('night_open', "Nighttime, in the village the perfect aesthetic, for a brutal unsolved homicide.  "),  # _08
    ('night_open', "Lights out remember , the dark, isn't empty it's just full of things, with very, sharp teeth. Ssshhh"),  # _09
    ('night_open', "Go to sleep the adults, are going to do some, light maiming. Heh heh heh"),  # _10
    ('night_open', "Time to rest, your weary heads one of you, won't have to worry, about waking up early ever again.  "),  # _11
    ('night_open', "Night falls it's time, for the daily transition from 'living' to 'past tense.'  "),  # _12
    ('night_open', "Close those eyes the last thing, you want to see is the disappointment, on the wolf's face, when they taste you. Ssshhh"),  # _13
    ('night_open', "Sleep tight don't let the bedbugs bite. The wolves, however are a completely, different story.  "),  # _14
    ('night_open', "Into the dark, we go please make sure, your wills, are easily accessible, on your nightstands. Ssshhh"),  # _15
    ('night_open', "The village, goes quiet the kind of quiet, that usually precedes, a lot of dramatic, blood splatter.  "),  # _16
    ('night_open', "Close your eyes just imagine, you're going under anesthesia , but without, the benefit, of a medical professional. Ssshhh  "),  # _17
    ('night_open', "Nighttime a lovely period, of unconsciousness right before, a permanent period, of unconsciousness. Heh heh"),  # _18
    ('night_open', "Go to sleep if you wake up , congratulations! You've successfully, delayed, the inevitable. Ssshhh"),  # _19
    ('night_open', "Night falls and the village collectively decides to ignore the sound of sharpening claws. Ssshhh go to sleep."),  # _20
    ('night_open', "Close your eyes and try to forget that the person sitting next to you is currently picking out a wine to pair with your liver."),  # _21
    ('night_open', "Lights out! It's time for the monsters to earn their keep and for you to earn your place in a coffin. Ssshhh"),  # _22
    ('night_open', "Sleep tight don't let the realization that you're totally doomed keep you from getting your eight hours.   "),  # _23
    ('night_open', "The darkness is here. It’s the perfect time for a little midnight snack. Try to be quiet while you're being eaten."),  # _24
    ('night_open', "Into the shadows we go. Remember: if you hear a growl it's probably just your neighbor's stomach. Or a wolf. Probably a wolf."),  # _25
    ('night_open', "Go to sleep, little sheep. The wolves have a very busy night planned, and they hate it when their food is restless."),  # _26
    ('night_open', "The sun is gone and with it, your safety. Close your eyes and pray the narrator likes you enough to let you wake up. Heh heh"),  # _27
    ('night_open', "Time for bed. If you wake up and find your roommate missing don't worry, they've just been promoted to 'Ghost.' Ssshhh"),  # _28
    ('night_open', "The village is silent. Well, except for the sound of someone being dragged into the woods. But ignore that sleep well."),  # _29
    # night_close
    ('night_close', "Good morning! please check yourself, for bite marks, and missing limbs."),  # _00
    ('night_close', "The sun is up! And surprise , someone's internal organs, are now, external. Let's investigate!"),  # _01
    ('night_close', "Wake up, villagers time to play everyone's favorite morning game , 'Whose blood is that?!'"),  # _02
    ('night_close', "Dawn breaks it smells like dew, fresh coffee and a distinct, lack of pulse."),  # _03
    ('night_close', "Morning, is here one of you, is noticeably less chatty, today. I wonder, why."),  # _04
    ('night_close', "Rise and shine! Unless you're the person, who got mauled to death. You can just, lie there."),  # _05
    ('night_close', "The village, wakes please try not to step, in the crime scene, on your way to breakfast."),  # _06
    ('night_close', "A new day! let's gather, around the fresh corpse, and pretend, we know what we're doing."),  # _07
    ('night_close', "Morning light, reveals a terrible truth , you are all, still terrible, at defending yourselves."),  # _08
    ('night_close', "Wakey, wakey time to fake your grief, and falsely accuse, your neighbors."),  # _09
    ('night_close', "The sun rises, revealing, that the wolves have , once again , outsmarted you, literal sheep."),  # _10
    ('night_close', "Good morning, to most of you to the deceased? My condolences, on your lack, of situational awareness."),  # _11
    ('night_close', "Dawn arrives the body count, has gone up , but on the bright side? there's more food to go around."),  # _12
    ('night_close', "Wake up. Someone, is dead. Let's try to act surprised even though this happens, literally, every night."),  # _13
    ('night_close', "Morning! Time to inspect the carnage , and draw, completely illogical, conclusions."),  # _14
    ('night_close', "The sun is shining! The birds are singing! And someone's throat has been ripped out. Lovely."),  # _15
    ('night_close', "Rise and shine let's start the day, with a healthy dose of trauma, and denial."),  # _16
    ('night_close', "Dawn breaks another night, survived. Let's see, who didn't make, the cut, this time around."),  # _17
    ('night_close', "Good morning, survivors! And a very quiet morning to the person, currently fertilizing, the daisies."),  # _18
    ('night_close', "Wake up the night has spoken , and its vocabulary, consists entirely, of violence. Heh heh"),  # _19
    ('night_close', "Good morning! The sun is up, and someone's life expectancy has officially hit zero. Let’s go see who it is!"),  # _20
    ('night_close', "Rise and shine! The birds are chirping, the dew is fresh and there’s a distinct lack of pulse in sector four."),  # _21
    ('night_close', "Wakey wakey! Time to find out which one of you is the guest of honor at today's funeral. Heh heh heh"),  # _22
    ('night_close', "Morning has broken and so has someone's ribcage. Let's gather 'round and pretend we're sad about it."),  # _23
    ('night_close', "The sun is up! Congratulations to those of you who still have all your limbs. To the rest better luck in the next life."),  # _24
    ('night_close', "Dawn reveals the carnage. It’s like a crime scene, but without the competent investigators. Let's see the damage!"),  # _25
    ('night_close', "Wake up, villagers! The night was productive for some and permanent for others. Shall we check the tally?"),  # _26
    ('night_close', "Good morning! I hope you all slept better than {eliminated_name} who, incidentally, will never sleep again. Heh."),  # _27
    ('night_close', "The village wakes and the census taker has some very bad news. One of you is now a 'former' resident."),  # _28
    ('night_close', "Rise and shine! It's a beautiful day for some baseless accusations and a light hanging. But first, the body count!"),  # _29
    ('night_close', "I love the smell of fresh betrayal in the morning. It smells like victory. And a little bit of copper."),  # _30
    ('night_close', "Wow, I'm shocked. Truly. Who could have guessed that the person you all trusted would end up being a killer? Oh wait, me."),  # _31
    # day_open
    ('day_open', "The floor, is open please begin, the senseless bickering, and baseless, finger-pointing."),  # _00
    ('day_open', "Time for the village meeting! Let's see, who can shout the loudest, without providing, any actual evidence."),  # _01
    ('day_open', "Accuse, away. I'm sure, your gut feeling, is much more reliable, than actual detective work. Heh."),  # _02
    ('day_open', "Let the witch hunt, commence remember , logic, is forbidden! We only run, on pure hysteria, here."),  # _03
    ('day_open', "Who, looks guilty? Probably the person, who just realized, they left the stove on , but let's hang them, anyway."),  # _04
    ('day_open', "Time to talk a fantastic opportunity, to watch you all, dig your own graves, with your mouths."),  # _05
    ('day_open', "The village, must act! Which is tragic , because your collective IQ, resembles the room temperature."),  # _06
    ('day_open', "Please begin, presenting your flawed theories the wolves, need a good laugh, before tonight's hunt. Heh heh"),  # _07
    ('day_open', "Discuss amongst yourselves whoever has, the most aggressive hand gestures, is probably, lying."),  # _08
    ('day_open', "Time to root out, the imposter or just bully, the quiet person. That's usually, your go-to strategy."),  # _09
    ('day_open', "Argue! Defend yourselves! It's like a courtroom drama , but everyone, is incompetent!"),  # _10
    ('day_open', "Let's hear your suspicions I've brought popcorn, for this absolute trainwreck, of a deduction. Ha!"),  # _11
    ('day_open', "The floor, is yours try not to falsely accuse the doctor, again , it's getting, embarrassing."),  # _12
    ('day_open', "Speak up! The imposter, is relying on your sheer stupidity, to survive. Don't, let them down!"),  # _13
    ('day_open', "Deliberate carefully or just flip a coin. The success rate, is exactly, the same. Heh."),  # _14
    ('day_open', "Time to find the killer look for the one, trying not to laugh, at your deduction skills."),  # _15
    ('day_open', "Let the paranoia-fueled debate, begin this is why humanity, is doomed, by the way."),  # _16
    ('day_open', "Who, do we trust, the least? A difficult question , in a room, full of habitual liars."),  # _17
    ('day_open', "Discuss the murder try to sound like you actually care, about the victim. It sells, the performance."),  # _18
    ('day_open', "The floor, is open please proceed, with your daily ritual, of collective self-sabotage."),  # _19
    ('day_open', "The floor is open! Please begin the ritual of accusing the person you like the least for absolutely no reason. Ha!"),  # _20
    ('day_open', "Time to talk! Let's see who can lie with the most confidence and who can believe them with the most stupidity."),  # _21
    ('day_open', "Discuss! Try to sound smart while you're actually just panicking and pointing fingers at the person with the loudest shirt."),  # _22
    ('day_open', "The village meeting is in session. Remember: facts are boring, but a good shouting match is what we’re really here for."),  # _23
    ('day_open', "Let the paranoia bloom! Who looks like they spent their night eating their friends? Don't all speak at once."),  # _24
    ('day_open', "Time for logic or whatever you people call that thing you do where you guess wrong three times in a row. Speak up!"),  # _25
    ('day_open', "The stage is yours. Try to act like you're not all just one bad accusation away from a complete mental breakdown."),  # _26
    ('day_open', "Who's the wolf? Is it the quiet one? The loud one? The one who's currently sweating through their shoes? Let's find out!"),  # _27
    ('day_open', "Deliberate carefully. The wolves are watching, and they really appreciate how much work you're doing for them. Heh."),  # _28
    ('day_open', "The floor is open please proceed to tear each other apart verbally, so the wolves don't have to do it physically tonight."),  # _29
    ('day_open', "I've seen more survival instinct in a bucket of fried chicken. But please, do go on with your 'strategy.'"),  # _30
    ('day_open', "If being wrong was a sport, this village would have several Olympic gold medals by now. Truly impressive."),  # _31
    ('day_open', "It's fascinating to watch you all. It's like watching a car crash in slow motion, but the cars are made of bad decisions."),  # _32
    ('day_open', "If I had a nickel for every time one of you made a smart move I’d be completely broke. Heh heh heh"),  # _33
    ('day_open', "The wolves aren't even trying anymore. They're just sitting back and watching you do their job for them. It's embarrassing, really."),  # _34
    ('day_open', "Please, tell us more about your 'gut feeling.' I'm sure it's much more accurate than, you know, basic observation."),  # _35
    ('day_open', "I'm sure that shouting slightly louder will make your completely baseless accusation more true. Please, continue."),  # _36
    ('day_open', "I love how confident you are when you're being 100% wrong. It's a special kind of talent, really."),  # _37
    ('day_open', "Oh, you think {eliminated_name} is the wolf because they 'looked at you funny'? Well, with that kind of logic, I'm sure we'll win in no time."),  # _38
    ('day_open', "Congratulations! You've narrowed it down to 'someone in this room.' We're practically halfway there!"),  # _39
    # vote_open
    ('vote_open', "Time to vote! Let's formally endorse, a terrible mistake."),  # _00
    ('vote_open', "The ballot, is open! Grab your pitchforks , and let mob mentality, take the wheel!"),  # _01
    ('vote_open', "Cast your votes it's time to legally sanction a murder, to avenge, an illegal murder."),  # _02
    ('vote_open', "Democracy! in action. Proving, that ten idiots, are vastly more dangerous, than one intelligent wolf."),  # _03
    ('vote_open', "Time to point, the finger please ensure your finger, is aimed at someone, you mildly dislike."),  # _04
    ('vote_open', "The moment, of truth Let's see, which innocent bystander, gets fed, to the metaphorical woodchipper?!"),  # _05
    ('vote_open', "Vote now! Remember , your hasty decision, will directly lead, to someone's demise. No, pressure!"),  # _06
    ('vote_open', "Cast your ballot! It's like voting for a politician , except the immediate death, is guaranteed."),  # _07
    ('vote_open', "Time to execute, someone make it count. Or don't. We all die, eventually, anyway."),  # _08
    ('vote_open', "The voting, has commenced! Let the frantic whispering, and desperate eye contact, begin."),  # _09
    ('vote_open', "Make your choice if you're wrong? the blood, is entirely on your hands. Have a great, day!"),  # _10
    ('vote_open', "Who, gets the rope, today?! Let's turn this tragedy, into a full-blown circus!"),  # _11
    ('vote_open', "Time to condemn, someone I suggest closing your eyes, and pointing , it's worked, for you, so far."),  # _12
    ('vote_open', "The ballot, is open! Let's see, who failed to win, the village popularity contest, today."),  # _13
    ('vote_open', "Cast your vote! Remember , the wolf is voting too and they're probably, laughing at you. Heh heh"),  # _14
    ('vote_open', "Time to choose, a scapegoat a time-honored human tradition, when faced, with complete ineptitude."),  # _15
    ('vote_open', "Voting time! please submit the name, of the person, whose vibe is slightly off, today."),  # _16
    ('vote_open', "The polls, are open! Your chance, to confidently make the situation, astronomically worse."),  # _17
    ('vote_open', "Vote carefully! Just kidding , your votes, are entirely driven, by panic, and spite. Ha!"),  # _18
    ('vote_open', "Let's tally, the votes I love seeing how confidently wrong, a group of people, can be. Heh heh heh"),  # _19
    ('vote_open', "Time to vote! Choose someone to die preferably someone who won't be missed. Which, in this group, is a lot of people."),  # _20
    ('vote_open', "The ballot is open! Democracy is great, isn't it? It allows a large group of people to be wrong together. Cast your votes!"),  # _21
    ('vote_open', "Point the finger! It’s the ultimate village tradition. Let’s see who gets the rope today! Heh heh heh"),  # _22
    ('vote_open', "Time to decide! Who’s going to be the village’s official mistake of the day? Don’t keep the executioner waiting."),  # _23
    ('vote_open', "Vote now! Remember, your choice matters! Well, it matters to the person you're about to murder, anyway."),  # _24
    ('vote_open', "The polls are open. Cast your ballot for the person you find most annoying. I mean the person you 'think' is a wolf. Same thing, right?"),  # _25
    ('vote_open', "Time to condemn! Let's see if you can actually hit a wolf this time, or if you're just going to keep thinning your own herd."),  # _26
    ('vote_open', "Make your choice. The rope is ready, the crowd is thirsty, and I've got a bet on how many innocents you can kill in a row. Ha!"),  # _27
    ('vote_open', "The voting has started. Please try to act like you have a reason for your choice. It makes the tragedy more entertaining."),  # _28
    ('vote_open', "Cast your vote! It's your civic duty to potentially murder a friend based on a hunch you had while eating a sandwich."),  # _29
    ('vote_open', "Oh, brilliant deduction! Truly, the Sherlock Holmes of our generation. Too bad you're pointing at a tree."),  # _30
    ('vote_open', "Good job, everyone! You've successfully managed to make a bad situation significantly worse. Gold star for you."),  # _31
    ('vote_open', "Is that your final answer? Because it's a terrible one. But hey, it's your funeral. Literally."),  # _32
    # vote_elimination
    ('vote_elimination', "{eliminated_name} the village has spoken. They think you're a monster , or just, annoying. Either way, get out."),  # _00
    ('vote_elimination', "Congratulations, {eliminated_name}! You've been elected, to the position, of 'Involuntary Exile.' Heh heh"),  # _01
    ('vote_elimination', "The votes, are in {eliminated_name} , you're officially the village's biggest mistake, of the day."),  # _02
    ('vote_elimination', "{eliminated_name}, is banished! Don't let the village gates, hit you on the way, to your certain doom."),  # _03
    ('vote_elimination', "Well, {eliminated_name} it seems your charming personality, wasn't enough, to save you, from a lynching."),  # _04
    ('vote_elimination', "The mob, has decided {eliminated_name} , please escort yourself, to the graveyard."),  # _05
    ('vote_elimination', "Farewell, {eliminated_name}! We'd say we'll miss you , but we literally, just voted, to get rid of you."),  # _06
    ('vote_elimination', "{eliminated_name}, departs let's hope, for your sake, they were actually a wolf. If not? awkward."),  # _07
    ('vote_elimination', "Out you go, {eliminated_name}! on the bright side , you no longer have to participate, in these stupid meetings."),  # _08
    ('vote_elimination', "The village, has cast out {eliminated_name} another brilliant display, of sheer, unadulterated guesswork."),  # _09
    ('vote_elimination', "{eliminated_name} your time, is up. Please leave your belongings , the survivors, will be looting them, shortly."),  # _10
    ('vote_elimination', "And {eliminated_name}, is gone a tragic victim, of democracy, and poor social skills. Heh."),  # _11
    ('vote_elimination', "Goodbye, {eliminated_name} you fought valiantly , but unfortunately, your defense, was pathetic."),  # _12
    ('vote_elimination', "The crowd, wants blood , and {eliminated_name}, is providing it. Thanks, for being a team player!"),  # _13
    ('vote_elimination', "{eliminated_name}, has been eliminated! I'm sure the real wolf, is very grateful, for your sacrifice. Ha!"),  # _14
    ('vote_elimination', "Look at you all, so proud, of eliminating {eliminated_name} I can't wait, to see your faces, when someone still dies, tonight."),  # _15
    ('vote_elimination', "Farewell, {eliminated_name} you were the weakest link. Goodbye."),  # _16
    ('vote_elimination', "{eliminated_name}, walks the path of exile may the road rise, to meet you , and the wolves out there, find you, quickly."),  # _17
    ('vote_elimination', "The village, rejects {eliminated_name} it's like a terrible breakup , but with more, public shaming."),  # _18
    ('vote_elimination', "{eliminated_name}, is banished! let's quickly move on, before the guilt, sets in."),  # _19
    # player_eliminated
    ('player_eliminated', "{eliminated_name}, was found dead apparently, reasoning with a hungry predator, doesn't work. Who knew?"),  # _00
    ('player_eliminated', "Tragic news , {eliminated_name}, is currently, resting in pieces. Heh heh"),  # _01
    ('player_eliminated', "{eliminated_name}, has been silenced on the bright side? they were a terrible conversationalist, anyway."),  # _02
    ('player_eliminated', "The night, claimed {eliminated_name} cleanup on aisle four, please."),  # _03
    ('player_eliminated', "Oh look , another corpse this time, it's {eliminated_name}. I'll add them, to the spreadsheet. Heh."),  # _04
    ('player_eliminated', "{eliminated_name}, didn't survive the night I told them, to lock their door , but did they listen? No."),  # _05
    ('player_eliminated', "We mourn, the loss of {eliminated_name} well, some of you do. The wolf, is just, digesting. Heh heh"),  # _06
    ('player_eliminated', "{eliminated_name}, has expired their warranty, has officially been voided, by a set of large teeth."),  # _07
    ('player_eliminated', "Dawn breaks , and {eliminated_name}, is noticeably less breathing, than yesterday."),  # _08
    ('player_eliminated', "Another soul, claimed {eliminated_name}, has crossed, the rainbow bridge. Violently. Bwahaha"),  # _09
    ('player_eliminated', "{eliminated_name}, was murdered if anyone wants their shoes? speak now, before they get bloodstained."),  # _10
    ('player_eliminated', "The darkness, was not kind, to {eliminated_name} mostly because, the darkness, had claws. Heh heh heh"),  # _11
    ('player_eliminated', "{eliminated_name}, is dead let's all pause, for a moment of silence.   okay, that's enough. Back to arguing."),  # _12
    ('player_eliminated', "We have a casualty , {eliminated_name} they lived a mediocre life, and died a highly dramatic death."),  # _13
    ('player_eliminated', "{eliminated_name}, has been permanently unsubscribed, from living. Heh."),  # _14
    ('player_eliminated', "Looks like {eliminated_name}, lost the game of hide and seek and their life."),  # _15
    ('player_eliminated', "{eliminated_name}, is no more they've joined, the choir invisible. And the local food chain. Heh heh"),  # _16
    ('player_eliminated', "The night took {eliminated_name} frankly, I thought they'd last, at least until Thursday. Disappointing."),  # _17
    ('player_eliminated', "{eliminated_name}, is dead please update, your emergency contact lists, accordingly."),  # _18
    ('player_eliminated', "A moment to recognize {eliminated_name} , who bravely served, as a midnight snack. Heh heh heh"),  # _19
    ('player_eliminated', "Bad news for {eliminated_name} they've been forcibly removed from the 'living' category. It was a short, unremarkable run."),  # _20
    ('player_eliminated', "Oh, look at that. {eliminated_name} has become a cautionary tale. Specifically, a tale about not being fast enough."),  # _21
    ('player_eliminated', "{eliminated_name} is no longer with us. They've gone to a better place. Or at least, a place where they don't have to listen to your theories."),  # _22
    ('player_eliminated', "We have a fresh opening in the village registry. {eliminated_name} decided to retire permanently. Heh heh heh"),  # _23
    ('player_eliminated', "I'd say {eliminated_name} will be missed, but let's be honest: they were mostly just taking up space. Onward!"),  # _24
    ('player_eliminated', "{eliminated_name} has met a very sharp, very furry end. I hope they were delicious. For the wolf's sake, of course."),  # _25
    ('player_eliminated', "The night has claimed another victim. {eliminated_name} is now a ghost. I wonder if they'll be any more useful in that form."),  # _26
    ('player_eliminated', "Farewell, {eliminated_name}. You were a mediocre villager, but you're a top-tier piece of evidence. Let's analyze the corpse!"),  # _27
    ('player_eliminated', "{eliminated_name} has expired. Their last thought was probably 'Wait, what was that noise?' Classic. Heh heh"),  # _28
    ('player_eliminated', "Another one bites the dust. {eliminated_name} is currently being recycled by nature. Circle of life, everyone! Bwahaha!"),  # _29
    ('player_eliminated', "Don't worry about the dead. They're much better off now they don't have to listen to your theories anymore."),  # _30
    ('player_eliminated', "Death is such a permanent solution to such a temporary problem as 'living in this village.' You're welcome!"),  # _31
    ('player_eliminated', "Another innocent dead? You guys are on a roll! If the goal is to kill everyone except the wolves, you're winning!"),  # _32
    # wolves_win
    ('wolves_win', "The wolves, win! A stunning victory, for natural selection , and a devastating blow, to your collective egos. Bwahaha!"),  # _00
    ('wolves_win', "The village, is dead the wolves, are full. I'd call this, a perfectly balanced ecosystem. Heh heh heh"),  # _01
    ('wolves_win', "Game over! The wolves, have devoured, everyone truly a triumph, of brawn , over whatever it is you guys, were using, instead of brains. Hahaha!"),  # _02
    ('wolves_win', "The imposters, win! You literally voted out, your own protection , and handed them, the keys. Astonishing. Ha!"),  # _03
    ('wolves_win', "Darkness, wins you're all dead. On the bright side? the village, will be very quiet, now. Heh heh"),  # _04
    ('wolves_win', "The wolves, howl in triumph! It's hard to feel bad, for the village , when they were, this spectacularly, incompetent. Bwahaha"),  # _05
    ('wolves_win', "Victory! Belongs to the wolf! Congratulations, on manipulating a group of people, who couldn't agree, on the color of the sky. Hahaha!"),  # _06
    ('wolves_win', "The village, has fallen it was less of a battle , and more of an all-you-can-eat buffet. Heh heh heh"),  # _07
    ('wolves_win', "Every precaution, failed , because your precautions, were terrible. The wolves, win. Good night. Ha!"),  # _08
    ('wolves_win', "The imposters, smile, as the last defender falls you guys, really made it, entirely too easy, for them. Heh heh"),  # _09
    ('wolves_win', "The wolves, take the crown! The villagers, take a permanent dirt nap. Perfectly, balanced. Bwahaha!"),  # _10
    ('wolves_win', "Game over! The bad guys, won. Welcome, to the real world, folks. Heh heh heh"),  # _11
    ('wolves_win', "The wolves, are victorious! I hope you're all happy, with your terrible choices, from the afterlife. Ha!"),  # _12
    ('wolves_win', "The village, has been, entirely consumed I'll send a postcard, to your next of kin. Wait , they're dead too. Hahaha!"),  # _13
    ('wolves_win', "Wolves, win! You put up a fight , but unfortunately, your weapons, were made, of sheer stupidity. Heh heh"),  # _14
    ('wolves_win', "The imposters, stand over the ruins it's amazing what a little teamwork , and pathological lying , can achieve. Bwahaha!"),  # _15
    ('wolves_win', "Darkness, swallows the village whole honestly, the real tragedy, is how long it took them, to finish you off. Heh heh heh"),  # _16
    ('wolves_win', "The wolves, have won! Let this be a lesson , never trust anyone, especially, yourselves. Ha!"),  # _17
    ('wolves_win', "The village, is wiped out at least you don't have to play, this agonizing game, anymore. Heh heh"),  # _18
    ('wolves_win', "Wolves, win! Flawless victory! Villagers , please proceed, to the nearest, existential crisis. Bwahaha!"),  # _19
    # village_wins
    ('village_wins', "The village, wins!? An absolute, statistical anomaly. I demand, a recount. Heh"),  # _00
    ('village_wins', "The last imposter, is dead! You survived! Mostly through dumb luck , but a win, is a win, I suppose."),  # _01
    ('village_wins', "Justice, prevails! You only had to murder, several innocent people, to find the guilty one. How heroic."),  # _02
    ('village_wins', "The wolves, are defeated! the village, is safe. Now you can go back, to dying of dysentery, like normal peasants."),  # _03
    ('village_wins', "Together! the village, triumphed. It's amazing, what you can accomplish , when you stop, actively sabotaging each other."),  # _04
    ('village_wins', "The hunt, is over! You won! Please don't let this temporary success, go to your incredibly, dense heads."),  # _05
    ('village_wins', "The village, stands victorious! I'm honestly shocked. I had already, written your eulogies. Ha!"),  # _06
    ('village_wins', "The imposters, are gone! Peace, returns I give it three days, before you start a civil war, over a fence dispute."),  # _07
    ('village_wins', "Light returns, to the village! The nightmare, is over! unfortunately, you still have to live, with each other."),  # _08
    ('village_wins', "The village, wins! Congratulations, on achieving the absolute bare minimum, requirement, of survival."),  # _09
    ('village_wins', "The wolves, have been, rooted out! You did it! I'll go cancel, the mass grave excavation."),  # _10
    ('village_wins', "Victory, for the village! Enjoy the PTSD, survivors! Heh heh"),  # _11
    ('village_wins', "The imposters, are vanquished! Let's celebrate , by pretending, we didn't casually betray each other, yesterday."),  # _12
    ('village_wins', "The village, is safe! You managed, to kill the monsters, before they finished, their appetizers. Well done."),  # _13
    ('village_wins', "Peace, returns at last! now you can return, to your mundane, miserable little lives. Ha!"),  # _14
    ('village_wins', "The last wolf, is gone! You won the game , but at what cost, to your morality?! Just kidding , you have none. Heh."),  # _15
    ('village_wins', "The village, survives! A truly disappointing day, for nihilists, everywhere. Heh heh"),  # _16
    ('village_wins', "You did it! the wolves, are dead. Feel free, to pat yourselves on the back, with your bloodstained hands."),  # _17
    ('village_wins', "The darkness, has been banished! Wow , you guys, actually coordinated a thought. I'm impressed. Ha!"),  # _18
    ('village_wins', "The village, wins! Drinks are on the house! mostly because, the bartender is dead , and we can just take them. Hahaha!"),  # _19
    ('village_wins', "The hunt, is over , the village, stands victorious and whole! Heh heh"),  # _20
]


def upgrade() -> None:
    narrator_scripts = sa.table(
        'narrator_scripts',
        sa.column('trigger_id', sa.String),
        sa.column('text', sa.Text),
    )
    op.execute(narrator_scripts.delete())
    op.bulk_insert(narrator_scripts, [
        {"trigger_id": t, "text": txt} for t, txt in _SEED_DATA
    ])


def downgrade() -> None:
    pass
