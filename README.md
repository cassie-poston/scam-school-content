# Scam School content

The scenario library for the **Scam School** iOS app. The app downloads it from:

**https://cassie-poston.github.io/scam-school-content/ScamLibrary.json**

Every change to `main` is checked automatically and, if it passes, published within a couple of minutes. Phones pick it up the next time the app opens, at most every 6 hours. No app update is needed.

## What's here

| Path | What it is |
| --- | --- |
| `content/scenarios/<category>.json` | The scenarios, one file per category |
| `content/library.json` | The categories (name, icon, description) |
| `tools/publish.py` | Checks every scenario and builds the file the app downloads |
| `.github/workflows/publish.yml` | Runs the check and publishes on every change |

## Adding or editing a scam

1. **Start from an official warning.** Use an alert from the FTC, FBI IC3, IRS, USPS Inspection Service, Social Security, or a state attorney general / consumer-protection office. Don't use AI to write or grade scenarios.
2. **Edit on github.com.** Open the category file, click the pencil icon, and copy an existing scenario as a template. Give it a new, unique `id`.
3. **Follow the rules** (the automatic check enforces them):
   - 2–4 short options, at least one with `"outcome": "safe"`.
   - `"costly"` options need a `"loss"` in dollars; `"safe"` options can't have one. `"risky"` means no money lost, but not the best move.
   - `redFlags`: up to 3 short tells. `safestAction`: one or two sentences.
   - `sources`: at least one `https://` link to the guidance you used.
   - Fictional people and companies, `555-01xx` phone numbers, and web addresses that don't belong to a real business. Real government agencies are fine.
   - `"trend": "emerging"` for newer schemes, otherwise `"evergreen"`.
4. **Get a second person to review it.** Choose *Create a new branch and start a pull request* when you save, and ask them to read it on the pull request page.
5. **Merge.** The check runs again, and if it passes the new version goes live.

To retire a scenario without deleting it, add `"active": false`.

## If the check fails

Open the **Actions** tab and click the failed run. The log says which scenario and what to fix, for example: `government.json [gov-dmv-ticket-text] option b: costly options need a loss`. When the check fails nothing is published, and phones keep the last good version.

The version number and date are set automatically from the commit history, so you never edit them.

## Checking locally (optional)

```bash
python3 tools/publish.py --check-links
```
