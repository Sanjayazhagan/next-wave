# Activate the scholarship demo on Azure

The prior update installed the form but omitted its public Caddy matcher.
The portal registry also needs an explicit merge into deployment configuration.
This patch fixes the matcher and supplies an idempotent configuration helper.
Only the fictional scholarship subtree bypasses Caddy login. Core service
authentication and every other application's authentication remain unchanged.

On the VM, from `browser-product`, after pulling this source update:

```bash
python3 scripts/configure_scholarship_practice.py --host gradientzero-browser26.eastasia.cloudapp.azure.com
python3 scripts/configure_scholarship_practice.py --host gradientzero-browser26.eastasia.cloudapp.azure.com --apply
docker compose -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml up -d --build api worker
docker compose -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml exec proxy caddy validate --config /etc/caddy/Caddyfile
docker compose -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml exec proxy caddy reload --config /etc/caddy/Caddyfile
curl -fsS https://gradientzero-browser26.eastasia.cloudapp.azure.com/practice/scholarship
```

Use the same Compose project/files/env source as the running deployment. If a
different env file is used, pass `--env-file <path>` to the helper. It prints no
secrets; it backs up the env file privately, preserves other portal entries and
leaves automated final submission disabled. Do not share its backup.

The authenticated bot bridge must open `{"portal_id":"scholarship_practice"}`.
It should receive a session instead of unknown-portal 422. A public form 200
alone does not prove this. Test synthetic field entry, the checkbox, citizen
approval, human Submit, and polling for a receipt and confirmed_by_portal=true.

## Bot checkbox contract

Bot code is not part of this checkout and was not changed. Its owner must
preserve checkbox nodes and explicitly collected consent in the planner/action
adapter. Send `type: "check"`, the observed checkbox target, `checked: true`,
`verified: true`, and `source_ref` identifying the actual citizen answer. Never
fabricate consent or infer it from an intention to apply. The synthetic-data
checkbox and final submission approval are distinct. Check the current browser
action schema when wiring the client; do not overwrite graph files with old
patches. No bot redeployment is required for a browser-only fix, but deploying
a new bot checkbox implementation does require its own release.

No Azure deployment or bot-level verification is claimed by this local patch.
