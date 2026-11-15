# support-bot-actions

A test of the GitHub Actions workflow that Modelpin for Jira's Setup tab (step 3) shows, run exactly as written.

- `.github/workflows/modelpin.yml` is Setup's snippet, copied from the app, with the one edit it asks for: the
  provider key. This bot uses Anthropic, so the step passes `ANTHROPIC_API_KEY` instead of `OPENAI_API_KEY`.
- The bot, its 8 scenarios, `modelpin.yaml` and the baseline in `.modelpin/` are copied from
  [samarthputhraya/support-bot](https://github.com/samarthputhraya/support-bot) (branch `main`): the baseline holds 10
  runs per scenario of `claude-sonnet-4-5-20250929`, recorded on 12 Nov 2026.
- A pull request that changes `app/model.txt` runs Modelpin 0.5.3 on the new model, compares it with the baseline, and
  sends the result to a Jira site with Modelpin for Jira installed, through `modelpin-relay` 0.1.1. The repository
  secrets `MODELPIN_WEBHOOK_URL` and `MODELPIN_WEBHOOK_SECRET` come from that site's Setup tab.

Built for Atlassian's Codegeist 2026 hackathon. The scenarios and baseline are a demo support bot's, not a real
shop's. Apache-2.0.
