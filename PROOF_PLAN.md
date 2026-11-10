# Proof plan

What counts as proof, and what does not. Status of ordering: the corpora and question were committed
before any probe ran (`29f8b1f`). This plan was written after the campaign harness first ran, so the
campaign itself is not pre-registered; its cases were written from the misuse list in the build brief
and every case is kept, passing or not.

1. Counterfactual matrix: same job, same repo, real Hermes loop, three configurations, two held steps.
2. Corpora, both directions: held rate on `eval/world.txt`, false-hold rate on `eval/everyday.txt`,
   every miss and false hold listed by line.
3. Break campaign: drift (commit, edit, branch, folder deleted), authority (stranger, empty owners,
   webhook text), replay (twice, two chats), expiry, seven disguises, five misbehaving-model cases,
   restart, fault switch.
4. Cost: model requests added by a park and by a drift refusal, counted at the provider.
5. One real run on Telegram with a real `git push` and `gh release create` on `0xkinno/abeyance-demo`.
   Not done yet. `docs/CODESPACES.md`.

The 66 unit tests and the 33 campaign cases are internal QA. The headline proof is the real run and the
published false-hold rate. The scripted model is Hermes's own test provider: it proves what Hermes and
Abeyance do with a given sequence of tool calls, not what any real model will choose to call.
