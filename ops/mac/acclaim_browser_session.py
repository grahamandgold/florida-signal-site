"""Choose one existing Acclaim session. Never create, navigate, or accept terms."""
import json
import sys
from urllib.parse import urlsplit


def analyze_inventory(inventory):
    candidates = []
    valid_id_count = 0
    for line in inventory.splitlines():
        fields = line.split('\t', 2)
        if len(fields) != 3 or not all(x.isdigit() for x in fields[:2]):
            continue
        valid_id_count += 1
        try:
            url = urlsplit(fields[2])
            if url.scheme != 'https' or url.hostname != 'officialrecords.broward.org' or url.port not in (None, 443) or url.username or url.password:
                continue
        except ValueError:
            continue
        path = url.path.lower().rstrip('/')
        if path == '/acclaimweb/search/searchtyperecorddate':
            state = 'READY'
        elif path == '/acclaimweb/disclaimer':
            state = 'TERMS'
        else:
            continue
        candidates.append((state, int(fields[0]), int(fields[1])))
    if len(candidates) > 1:
        selection = ('AMBIGUOUS', 0, 0)
    else:
        selection = candidates[0] if candidates else ('MISSING', 0, 0)
    return selection, valid_id_count, len(candidates)


def select_session(inventory):
    return analyze_inventory(inventory)[0]


def selection_output(argv):
    selection, valid_ids, candidates = analyze_inventory(argv[0])
    output = '|'.join(map(str, selection))
    if len(argv) == 1:
        return output
    if len(argv) != 6 or argv[1] != '--diagnostic' or argv[2] not in ('true', 'false'):
        raise ValueError('Invalid diagnostic arguments')
    if not all(value.isascii() and value.isdigit() for value in argv[3:]):
        raise ValueError('Invalid diagnostic counts')
    running = argv[2] == 'true'
    windows, tabs, official = map(int, argv[3:])
    diagnostic = {
        'stage': 'inventory_selection' if running else 'chrome_running_check',
        'chrome_running': running, 'window_count': windows, 'tab_count': tabs,
        'official_prefix_count': official, 'parser_valid_id_count': valid_ids,
        'candidate_count': candidates, 'selection': selection[0],
    }
    # Only a fixed schema of categories, booleans and counts is exported. The
    # inventory, URL/query text and browser IDs never enter the diagnostic.
    return output + '\n' + json.dumps(diagnostic, sort_keys=True, separators=(',', ':'))


if __name__ == '__main__':
    try:
        print(selection_output(sys.argv[1:]))
    except (IndexError, ValueError):
        print('Acclaim session input or diagnostic arguments invalid', file=sys.stderr)
        raise SystemExit(2)
