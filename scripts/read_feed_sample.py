import itertools
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared import constants  # noqa: E402


def main() -> None:
    events = []
    with httpx.Client(timeout=30.0) as client:
        with client.stream("GET", f"{constants.registry_base_url()}{constants.API_FEED}", headers={"accept": "text/event-stream"}) as r:
            r.raise_for_status()
            for line in itertools.islice(r.iter_lines(), 0, 200):
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
                try:
                    events.append(json.loads(payload))
                except Exception:
                    continue
                if len(events) >= 8:
                    break

    print(json.dumps([e.get("type") for e in events], indent=2))


if __name__ == "__main__":
    main()

