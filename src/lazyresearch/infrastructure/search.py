"""Bounded SerpApi adapter. Discovery snippets never enter evidence storage."""

import http.client
import json
import socket
from threading import Event, Timer
from time import perf_counter
from urllib.parse import urlencode

from lazyresearch.application.mission_models import MissionError, SearchHit, TransientMissionError
from lazyresearch.application.mission_rules import public_query


class SerpApiSearch:
    def __init__(self, api_key: str, timeout: float = 20, max_results: int = 10) -> None:
        if not 1 <= timeout <= 60 or not 1 <= max_results <= 10:
            raise ValueError("invalid search bounds")
        self._key, self.timeout, self.max_results = api_key, timeout, max_results

    def search(self, query: str, limit: int) -> tuple[SearchHit, ...]:
        if not self._key:
            raise MissionError("SEARCH_NOT_CONFIGURED")
        if not query or query != public_query(query):
            raise MissionError("UNSAFE_QUERY")
        count = min(max(1, limit), self.max_results)
        conn = http.client.HTTPSConnection("serpapi.com", timeout=self.timeout)
        timer = None
        handle = None
        expired = Event()
        started = perf_counter()
        try:
            conn.connect()
            assert conn.sock is not None
            handle = conn.sock.dup()

            def abort() -> None:
                expired.set()
                try:
                    assert handle is not None
                    handle.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            timer = Timer(max(0.001, self.timeout - (perf_counter() - started)), abort)
            timer.daemon = True
            timer.start()
            conn.request(
                "GET",
                "/search.json?"
                + urlencode({"engine": "google", "q": query, "api_key": self._key, "num": count}),
                headers={"Accept": "application/json"},
            )
            response = conn.getresponse()
            if response.status == 429 or response.status >= 500:
                raise TransientMissionError("SEARCH_TRANSIENT")
            if response.status != 200:
                raise MissionError("SEARCH_REJECTED")
            raw = response.read(1024 * 1024 + 1)
            if expired.is_set():
                raise TransientMissionError("SEARCH_TIMEOUT")
            if len(raw) > 1024 * 1024:
                raise MissionError("SEARCH_RESPONSE_TOO_LARGE")
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("error"):
                raise MissionError("SEARCH_INVALID_RESPONSE")
            hits = []
            for rank, item in enumerate(data.get("organic_results", [])[:count], 1):
                if isinstance(item, dict) and isinstance(item.get("link"), str):
                    hits.append(
                        SearchHit(
                            url=item["link"],
                            title=str(item.get("title", "Public source"))[:500],
                            snippet=str(item.get("snippet", ""))[:1500],
                            rank=rank,
                            provider_id=str(item["position"]) if "position" in item else None,
                        )
                    )
            return tuple(hits)
        except (TimeoutError, OSError, http.client.HTTPException):
            raise TransientMissionError("SEARCH_UNAVAILABLE") from None
        except (ValueError, TypeError):
            raise MissionError("SEARCH_INVALID_RESPONSE") from None
        finally:
            if timer is not None:
                timer.cancel()
            if handle is not None:
                handle.close()
            conn.close()
