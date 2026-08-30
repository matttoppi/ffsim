# Rank-20 route decision-impact check

Compare each rank-20 one-turn route leader with the frozen terminal leader from the six-state full 300-rollout corpus.

For each state, rerun exactly the terminal leader and rank-20 route leader with 300 coupled continuations under the unchanged live population distribution and terminal scorer.

The route screen passes only if every rank-20 route leader is a terminal practical co-leader under the existing 0.1-point paired gate. Passing does not authorize route ranking; it only permits a later conservative-screening experiment. Failure keeps rank-20 as return-evidence shadow only.

No manager mixture, rank-20 probability, or route score enters the terminal evaluation.