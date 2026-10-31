# Chaos script (M6)

`chaos.js` breaks a live form page in realistic, repeatable ways so the agent's
self-repair can be shown live. It only changes the page inside our own browser
session. **It never changes `name` attributes, `id` attributes or form values**,
because the portal's server and scripts depend on them.

```js
window.__chaos({mode: "rename", seed: 7, count: 3})   // returns [{mode, target, from, to}, ...]
window.__chaosLog                                     // every entry so far
```

| Mode | What breaks |
| --- | --- |
| `rename` | label text, `placeholder` and `aria-label` replaced with a synonym ("Annual family income" → "Family income per annum"); breaks label-based locators |
| `rewrap` | the field's group wrapped in 2 extra `div`s with random classes; breaks positional XPaths and nth-child selectors |
| `move` | field groups in a container of 3 or more shuffled (seeded Fisher-Yates) |
| `hide` | a field group moved inside a closed `<details><summary>More details</summary>` |
| `popup` | a full-screen `role=dialog` "Important notice" with a Close button |
| `slow` | `fetch` and `XMLHttpRequest.send` delayed 2 to 6 seconds |

Every random choice goes through a seeded PRNG (`mulberry32`), so the same seed
on the same page gives the same changes. Evaluating the file twice is a no-op.

## Calling it from the browser worker

`contracts/browser.py` defines `POST /session/{id}/inject` with
`InjectRequest {script, options}`. Send the file's text as `script` and the
chaos options as `options`:

```python
script = Path("modules/chaos/chaos.js").read_text()
InjectRequest(script=script, options={"mode": "rename", "seed": 7, "count": 3})
```

The worker then runs, on the session's page:

```python
await page.evaluate(request.script)                                  # installs window.__chaos once
log = await page.evaluate("opts => window.__chaos(opts)", request.options)
```

To keep it across navigations, use `page.add_init_script(request.script)` as
well. Return or emit `log` so the web app can show what was broken.

Note: the browser teammate's branch uses named scripts (`rename_income`,
`popup`, ...). This file follows `main`'s `InjectRequest {script, options}`.

## Local check

```bash
uv run python -m modules.chaos.run_local
```

For every mode and three seeds it loads `test_form.html`, injects chaos, fills
every field by `name`, opens any `<details>`, closes any popup, submits, and
checks the submitted values are exactly what was filled, and that the same seed
gives the same log. All 6 modes pass.
