"""Choose one existing Acclaim session. Never create, navigate, or accept terms."""
import sys
from urllib.parse import urlsplit


def select_session(inventory):
    candidates = []
    for line in inventory.splitlines():
        fields = line.split('\t', 2)
        if len(fields) != 3 or not all(x.isdigit() for x in fields[:2]):
            continue
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
        return ('AMBIGUOUS', 0, 0)
    return candidates[0] if candidates else ('MISSING', 0, 0)


if __name__ == '__main__':
    print('|'.join(map(str, select_session(sys.argv[1]))))
