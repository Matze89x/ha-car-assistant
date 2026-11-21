# Maintaining: from a report to a version

🇬🇧 English · [🇩🇪 Deutsch](maintaining.de.md)

How reports and contributions become the next version. Contributors never touch the version - the maintainers bundle it.

## The way of a change

1. **Report or pull request** comes in (an issue with a template, or a pull request from a fork - also one made with an AI assistant).
2. **Triage:** it gets the label `needs-triage`, then `accepted`, `needs-info`, `needs-decision` or `wontfix`. Questions and ideas go to *Discussions*.
3. **Bundle:** accepted work is put into a **milestone** named like the next version, for example `0.5.1 Beta`. A fix release collects about 4-5 corrections or small improvements.
4. **Merge** the pull requests of the milestone into `main` (CI must be green, the code owner reviews).
5. **Version:** the maintainer runs `python tools/release.py fix "English line" "Deutsche Zeile"` once per bundle (a new feature: `feature`). It counts the number up and writes it into every place and both changelogs.
6. **Tag and release:** `git tag v0.5.1-beta`, then *Releases → Draft a new release → Generate release notes* (sorted by label, see `.github/release.yml`).

## Version numbers

`RELEASE.FEATURES.FIXES` plus the stage (Alpha / Beta): the first number counts releases, the second features, the third fixes and corrections. Only `release.json` holds the value; `tools/release.py` writes it everywhere. See [CONTRIBUTING](../CONTRIBUTING.md).

## Labels and automation

- Labels are listed in `.github/labels.yml`; *Actions → Sync labels → Run workflow* creates them.
- `.github/CODEOWNERS` makes every pull request wait for the maintainer.
- `.github/dependabot.yml` proposes library updates; `.github/workflows/ci.yml` runs the tests on every push and pull request.

## Settings of the repository (once)

A short list lives in the maintainer's checklist: a branch rule for `main` (pull request, CI must pass, code owner review, no force push), *Actions* approval for first-time contributors and a read-only token, *Discussions* on, private vulnerability reporting, Dependabot alerts, secret scanning with push protection.
