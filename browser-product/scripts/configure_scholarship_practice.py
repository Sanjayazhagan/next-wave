"""Merge the fictional portal into a deployment .env; dry-run unless --apply.

Does not print secrets, deploy, or change final-submit/auth settings.
"""
import argparse
import json
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit

PATTERN = r'Receipt: (DEMO-SCH-[A-F0-9]{12}-[A-F0-9]{32})'


def configure(text, host):
    parsed = urlsplit('https://' + host)
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host) or not parsed.hostname or '.' not in host:
        raise ValueError('Use the public DNS hostname only, without a scheme or path')
    updates = {}
    for key in ('BROWSER_PORTALS_JSON', 'BROWSER_ALLOWED_ORIGINS'):
        matches = re.findall(r'^\s*' + key + r'=(.*)$', text, re.M)
        if len(matches) > 1:
            raise ValueError('Duplicate ' + key + ' entries; resolve manually')
        value = matches[0].strip() if matches else ''
        if value[:1] in ("'", '"'):
            if value[-1:] != value[:1]:
                raise ValueError('Unbalanced quoting for ' + key)
            value = value[1:-1]
        updates[key] = value
    try:
        portals = json.loads(updates['BROWSER_PORTALS_JSON'] or '{}')
    except ValueError:
        raise ValueError('Invalid portal JSON; fix existing configuration first') from None
    if not isinstance(portals, dict):
        raise ValueError('Portal registry must be an object')
    origin = 'https://' + host
    portals['scholarship_practice'] = {'url': origin + '/practice/scholarship', 'receipt_pattern': PATTERN}
    updates['BROWSER_PORTALS_JSON'] = "'" + json.dumps(portals, separators=(',', ':')).replace("'", '\\u0027') + "'"
    origins = [v.strip() for v in updates['BROWSER_ALLOWED_ORIGINS'].split(',') if v.strip()]
    if origin not in origins:
        origins.append(origin)
    updates['BROWSER_ALLOWED_ORIGINS'] = ','.join(origins)
    for key, value in updates.items():
        line = key + '=' + value
        if re.search(r'^\s*' + key + '=', text, re.M):
            text = re.sub(r'^\s*' + key + r'=.*$', lambda _: line, text, flags=re.M)
        else:
            text = text.rstrip('\n') + '\n' + line + '\n'
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--host', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    original = args.env_file.read_text(encoding='utf-8')
    updated = configure(original, args.host)
    if args.apply and updated != original:
        backup = args.env_file.with_name(args.env_file.name + '.practice-backup-' + str(time.time_ns()))
        shutil.copy2(args.env_file, backup)
        args.env_file.write_text(updated, encoding='utf-8')
        print('Updated portal registry/origin only. Private backup beside env file; do not share it.')
    else:
        print('Configuration validated. No file changes.' if not args.apply else 'Already configured.')


if __name__ == '__main__':
    main()
