# Review of reported deployment issues — 2026-11-01

## Verification conclusions

| Reported item | Code finding | Required live check |
| --- | --- | --- |
| `/core-assist/` was 404 | Caddy already matched `/core-assist/*` but FastAPI only served `/core-assist/{task_id}`. Added a safe 200 landing page, with no session data. | Check bare URL and one freshly created invitation on Azure after restart. |
| Expected commit `49ed519` | User already reported Azure/GitHub both at `f770c8f`, which supersedes the old commit. | Run `git rev-parse --short HEAD` and `git rev-parse --short origin/feat/browser-product` after fetch, record deploy hash. |
| CAPTCHA `image_base64` missing | Intentionally **not** exporting cropped/whole-page CAPTCHA images. Snapshot challenge now explicitly advertises `delivery_mode: human_assistance_link`, `human_task_reason`, `requires_human: true`, `image_base64: null`; iframe-only challenges also advertise a task. | Teammate must change bot branch: detect delivery mode, issue a human task and send invitation, not expect base64. Test the same-session challenge and completion on an authorized fixture. |
| Upload `Submit` returned 403 | Dedicated upload-form classification and scoped intermediate POST have tests. | Requires external Azure test using synthetic PDF on an authorized practice portal; successful API action **alone** does not prove website receipt. |

## Telegram / agent contract for CAPTCHA and OTP

For a snapshot with `challenge.kind` `captcha` or `otp` and `challenge.delivery_mode == "human_assistance_link"`:

1. The **trusted bot backend** requests `POST /core-browser/session/{sid}/human-task` with `{ "reason": challenge.human_task_reason, "ttl_seconds": 300 }` using `X-Internal-Key` *server-side only*.
2. Send `assistance_url` privately to the citizen; never send its fragment/token to the language model or logs.
3. Poll `GET /core-browser/session/{sid}/human-task` until the human returns control. Reinspect the page to verify the state moved forward; task completion alone does **not** prove CAPTCHA or OTP validation.
4. Handle expired/missing links by asking the person to request a new invitation. Do not automatically solve/bypass CAPTCHA.

This does **not** send `image_base64`, and existing bot logic that only looks for `image_base64` must be changed by the teammate. Do not claim the bot is fixed until that happens.

## Azure safe checks

```bash
cd ~/next-wave/browser-product
git fetch origin
git log -1 --oneline
git rev-parse --short origin/feat/browser-product
sudo docker compose --env-file .env -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml ps
curl -fsS http://127.0.0.1:8100/ready
curl -sS -o /dev/null -w 'Assistance landing HTTP %{http_code}\n' https://gradientzero-browser26.eastasia.cloudapp.azure.com/core-assist/
sudo docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

For a **fresh task only**, open its full invitation privately. A 200 on `/core-assist/` alone does not prove the capability link, session or challenge controls work.

`BROWSER_ENABLE_FINAL_SUBMIT=false` stays unchanged. Neither 8100 nor 8101 should be publicly exposed. Only add an exact origin to `BROWSER_INTERMEDIATE_POST_ORIGINS` after reviewing an authorized portal workflow; do not enable wildcard POSTs.

## Scope / limits

This package is an offline code update. It was not pushed, deployed to Azure, nor tested against a live external upload portal here. A separate live upload test and actual bot handoff remain owner/teammate work. Do not send secrets, full assistance URLs, or citizen data in result reports.
