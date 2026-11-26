# Lessons 1-3: the first concepts

Each lesson has a **goal**, 3-5 **bite-size screens**, a **recall question**, and a **teach-card template** using `{placeholder}` slots only. No frequencies, EVs, bet sizes, or invented spots. The engine fills every slot from verified data; this file only says what is *said* and in what order.

Gate types: the first two screens of each lesson are `none` or `recognize`; the final screen is `solve` and is engine-graded. A graded screen always shows the teach card after a miss.

---

# Lesson 1 — Value vs bluff

**Goal:** the learner can say, in their own words, the two reasons a person puts money into a pot — to be called by a worse hand (value), or to make a better hand fold (bluff) — and can tell which one a given action is trying to do.

### Screen 1.1 — Two reasons to bet
`visual: action_ring` `gate: none`
> People put money in for two different reasons. One: you think your hand is best right now, and you want a worse hand to pay you. Two: you think your hand is not best, and you want a better hand to fold instead.

### Screen 1.2 — Betting to be called
`visual: chips_to_center` `gate: none`
> When you bet hoping a worse hand calls, that is a **value** bet. You are not trying to scare anyone away. Being called is the point.

### Screen 1.3 — Betting to make them fold
`visual: folded_cards` `gate: none`
> When you bet hoping a better hand gives up, that is a **bluff**. You are happy to win without a showdown. Being called is usually bad news.

### Screen 1.4 — The same bet, two purposes
`visual: action_ring` `gate: recognize`
> The same size of bet can be either one. What makes it value or a bluff is what you *want* to happen next — a call, or a fold. Tap which purpose this action is trying to serve.

### Screen 1.5 — Practice
`visual: spot_frame` `gate: solve`
> Here is a real spot. Decide what to do. After it is graded you will see what the better choice was and why.

### Recall 1
**Question:** Name the two reasons to put money into a pot.
**Answer key:** to be called by a worse hand (value); to make a better hand fold (bluff).

### Teach-card template — Lesson 1
> You chose **{chosen_action}**. The better choice was **{best_action}**.
>
> That choice was better because {grade_reason}.
>
> In this spot your hand {hand_strength_phrase}. The purpose of the better action here was {purpose_phrase} — {purpose_explanation}.
>
> **Value** wants a call. **Bluff** wants a fold. Ask yourself which one you are after before you act.

Slots: `{chosen_action}`, `{best_action}`, `{grade_reason}`, `{hand_strength_phrase}`, `{purpose_phrase}`, `{purpose_explanation}` — all engine-supplied or chosen from a fixed phrase set defined in `teach-card-template.json`. No slot may be filled with a frequency or an EV.

---

# Lesson 2 — Pot odds in plain words

**Goal:** the learner understands that when it costs them something to stay in, they are comparing what they must pay against what is already out there, and can say this in their own words without formulas.

### Screen 2.1 — What is already in the pot
`visual: pot_stack` `gate: none`
> The money in the middle is the pot. It belongs to nobody until the hand ends. It is the prize everyone is playing for.

### Screen 2.2 — Paying to stay
`visual: chips_to_center` `gate: none`
> When it is your turn and there is a bet to you, staying in costs money. Fold, and you keep that money but give up the pot. Call, and you pay to stay.

### Screen 2.3 — What you get for what you pay
`visual: pot_stack` `gate: none`
> The question is simple: is what I must pay small next to what I could win? If the pot is large and the price is small, staying is often worth it. If the pot is small and the price is large, it usually is not.

### Screen 2.4 — Sometimes the price is the same
`visual: pot_stack` `gate: recognize`
> Two hands, two different prices, both offered the same pot. Tap the one where paying is the better deal for the money at stake. There is no formula to memorise — just look at price next to pot.

### Screen 2.5 — Practice
`visual: spot_frame` `gate: solve`
> A real spot. The engine knows the pot and the price; you decide. The teach card will show the numbers it used, never ones you invented.

### Recall 2
**Question:** In one sentence, what are you comparing when you decide whether to call a bet?
**Answer key:** what it costs you to stay against what is already in the pot (what you could win).

### Teach-card template — Lesson 2
> You chose **{chosen_action}**. The better choice was **{best_action}**.
>
> It would have cost **{cost_to_call}** to stay, and the pot held **{pot_size}** before your decision. So you were paying **{cost_to_call}** to try to win **{pot_size}**.
>
> {pot_odds_verdict_phrase}
>
> You do not need a formula. Ask: is this price small next to this pot?

Slots: `{cost_to_call}`, `{pot_size}` — **numeric, engine-supplied from the verified spot only.** `{chosen_action}`, `{best_action}`, `{pot_odds_verdict_phrase}` from the fixed phrase set. This is the one lesson whose teach card may show numbers, and every one of them comes from the spot record, never from this content file.

---

# Lesson 3 — Why mixed plays exist

**Goal:** the learner accepts that more than one action can be genuinely correct in the same spot, and does not read "the solver also sometimes does the other thing" as a mistake or a rule to copy.

### Screen 3.1 — Two good answers
`visual: split_choice` `gate: none`
> In some spots, two different choices are both good. Not close, and not a tie you have to guess — genuinely fine. Strong players mix them on purpose.

### Screen 3.2 — Why mix
`visual: split_choice` `gate: none`
> If you always did the same thing in the same spot, anyone paying attention would know what you hold. Mixing keeps your play from being readable.

### Screen 3.3 — Mixed is not random
`visual: split_choice` `gate: none`
> Mixing does not mean flipping a coin. It means the situation supports more than one good choice, and you pick among the good ones. The bad choices stay bad.

### Screen 3.4 — How it is graded
`visual: grade_meter` `gate: recognize`
> When a spot is genuinely mixed, picking *either* good choice counts as a hit. You are not punished for the one the engine happened to list first. Tap to confirm you understand.

### Screen 3.5 — Practice
`visual: spot_frame` `gate: solve`
> A real spot, possibly a mixed one. Decide. If it is mixed, both good choices will be accepted, and the teach card will say so.

### Recall 3
**Question:** If a spot is mixed, are you wrong for choosing the other good action?
**Answer key:** No. Both good actions count as correct; mixing is not guessing.

### Teach-card template — Lesson 3
> You chose **{chosen_action}**. {mixed_verdict}.
>
> {mixed_explanation}
>
> Remember: when a spot is mixed, more than one choice is good. When it is not mixed, only the best choice is.

Slots: `{chosen_action}`, `{best_action}`, `{mixed_verdict}`, `{mixed_explanation}` from the fixed phrase set. `{mixed_verdict}` is one of two fixed sentences: "This spot was mixed — your choice was one of the good ones." or "This spot was not mixed; the better choice was {best_action}."

---

# Review: the through-line

By the end of Lesson 3 the learner should hold three sentences:

1. People bet to be called (value) or to make others fold (bluff).
2. Calling costs something; compare the price to the pot.
3. Sometimes more than one choice is good, and that is on purpose.

These three are the whole beginner curriculum. Everything after this is detail on top of them.

# What these lessons must never do

- Present a frequency, an EV, or a bet size as advice. Only the Lesson 2 teach card shows numbers, and only from the spot record.
- Tell the learner a specific hand is "right" to play without the engine grading it on a real spot.
- Hide the teach card on a miss or a glance (per #185).
- Mock the learner for a wrong choice. A miss is the lesson arriving.
