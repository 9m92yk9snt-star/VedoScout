# Actual model experiments: Orman400

These are standalone source-image experiments, not production report latency.
Expected reference answers are evaluated after requests, never supplied as input.
No merge or deployment is justified by the results so far.

| Run | Preparation | Model phase | Reference matches | Quality |
| --- | --- | --- | --- | --- |
| 39138207424 | 17.809 s | 175.529 s | 0/5 | Two of three calls timed out; remaining response misattributed the goal. |
| 39139382430 | 16.540 s | 184.007 s | 2/5 | All 12 calls returned; saved shot and goal matched. All three assists missing, with additional incorrect scoring events. |

Run 2 uses source-image scene candidates, raw selection consensus, 8 fps and
low reasoning effort. The evaluator's two time matches are not independent
visual proof. Raw responses are preserved in each run's evidence artifact.
All five production code verification jobs at fc5f535 passed; code checks do
not prove football perception.

Inspection of the actual raw responses identified perceptual errors before
the resolver: sequence_007 calls a white recipient a blue opponent;
sequence_008 invents an intervening pass; followup_002 assigns the selected
identity to white #10. Sequence_006 conflates adjacent play contexts. Source
image changes are candidates, not reliable edit boundaries on the same pitch.
Removing causal checks would turn these errors into confident wrong statistics.

## Controlled resolution comparison

Next run changes only preparation's maximum image edge from 768 to 1280.
Same source checksums, ten raw references, model, 8 fps, prompt, packet plan,
two workers, reasoning effort, follow-up rules and budgets are retained.
The source stays uncropped. No action time or expected outcome determines
which images receive more pixels. Offline preparation retained all 622 sampled
instants and 704 packet appearances. All ten initial wire requests fit the
19.5 MB cap; largest is 14,917,983 bytes. This establishes deliverability,
not a prediction that the model will recover the missing assists.

The source video and original taps were published as test input with the
owner's explicit permission. Credentials remain in GitHub Actions secrets.
