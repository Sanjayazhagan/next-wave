"""Generates app/translations_generated.json from the fixed English messages.

Run once, and again when the messages change. The fixed messages hold no personal
data. The output is machine-translated and should be reviewed by native speakers.

    uv run python -m scripts.generate_translations
"""
import asyncio
import json
import re
from pathlib import Path

import httpx

from app.config import Settings
from app.translations import HINDI

LANGUAGES = {
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi in Gurmukhi script",
    "or": "Odia",
    "ur": "Urdu",
}
OUTPUT = Path(__file__).parent.parent / "app" / "translations_generated.json"
BATCH_SIZE = 12
PAUSE_SECONDS = 25
ATTEMPTS = 5
PLACEHOLDER = re.compile(r"\{\w+\}")

SYSTEM = """You translate messages for Dakiya, a chat assistant that helps Indian students
apply for government schemes. Translate into {language}, in that language's own script.
Use simple words that a school student and their parents use every day.
Address the reader politely. Keep button labels very short.
Keep these unchanged: anything in curly braces such as {{number}}, and the words OTP, PDF,
ID, AI, STOP, /start, Aadhaar, BC, MBC, SC, ST, B.E.
Keep line breaks and numbers as they are. Call the Done button by its translated name.
Reply with only a JSON object using the same keys as the input."""


def valid(english: str, translated: object) -> bool:
    return (
        isinstance(translated, str)
        and bool(translated.strip())
        and sorted(PLACEHOLDER.findall(english)) == sorted(PLACEHOLDER.findall(translated))
    )


async def translate_batch(
    http: httpx.AsyncClient, settings: Settings, language: str, batch: list[str]
) -> dict[str, str]:
    source = {str(index): text for index, text in enumerate(batch)}
    for attempt in range(ATTEMPTS):
        response = await http.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "temperature": 0,
                "max_tokens": 3000,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM.format(language=language)},
                    {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
                ],
            },
            timeout=90,
        )
        if response.status_code == 429:
            wait = float(response.headers.get("retry-after", 30))
            print(f"  rate limited, waiting {wait:.0f}s", flush=True)
            await asyncio.sleep(min(wait + 1, 70))
            continue
        response.raise_for_status()
        try:
            reply = json.loads(response.json()["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError):
            print(f"  unreadable reply, attempt {attempt + 1}", flush=True)
            continue
        if all(valid(text, reply.get(key)) for key, text in source.items()):
            return {text: reply[key].strip() for key, text in source.items()}
        print(f"  invalid translation, attempt {attempt + 1}", flush=True)
    raise RuntimeError(f"Could not translate a batch into {language}")


async def main() -> None:
    settings = Settings()
    english = list(HINDI)
    done: dict[str, dict[str, str]] = {}
    if OUTPUT.exists():
        done = json.loads(OUTPUT.read_text(encoding="utf-8"))

    async with httpx.AsyncClient() as http:
        for code, language in LANGUAGES.items():
            table = done.get(code, {})
            todo = [text for text in english if text not in table]
            print(f"{language}: {len(todo)} to do", flush=True)
            for start in range(0, len(todo), BATCH_SIZE):
                batch = todo[start : start + BATCH_SIZE]
                table.update(await translate_batch(http, settings, language, batch))
                done[code] = table
                OUTPUT.write_text(
                    json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8"
                )
                await asyncio.sleep(PAUSE_SECONDS)
    print("finished", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
