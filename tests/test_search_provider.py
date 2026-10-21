import json

import pytest

from lazyresearch.application.mission_models import MissionError, TransientMissionError
from lazyresearch.infrastructure.search import SerpApiSearch


class Socket:
    def dup(self):
        return self

    def shutdown(self, mode):
        pass

    def close(self):
        pass


@pytest.mark.parametrize(
    "status,expected",
    [(200, None), (401, MissionError), (429, TransientMissionError), (503, TransientMissionError)],
)
def test_serpapi_transport_bounds_and_safe_errors(monkeypatch, status, expected):
    calls = []

    class Connection:
        sock = Socket()

        def __init__(self, host, timeout):
            assert host == "serpapi.com" and timeout == 20

        def connect(self):
            pass

        def request(self, method, path, headers):
            calls.append((method, path))

        def getresponse(self):
            return self

        def read(self, limit):
            assert limit == 1024 * 1024 + 1
            return json.dumps(
                {
                    "organic_results": [
                        {
                            "link": "https://example.com",
                            "title": "Battery",
                            "snippet": "discovery only",
                        }
                    ]
                }
            ).encode()

        def close(self):
            pass

    Connection.status = status
    monkeypatch.setattr(
        "lazyresearch.infrastructure.search.http.client.HTTPSConnection", Connection
    )
    provider = SerpApiSearch("synthetic-secret", max_results=1)
    if expected:
        with pytest.raises(expected) as caught:
            provider.search("battery", 10)
        assert "synthetic-secret" not in str(caught.value)
    else:
        hits = provider.search("battery", 10)
        assert len(hits) == 1 and hits[0].snippet == "discovery only"
    assert "num=1" in calls[0][1]


def test_serpapi_missing_key_and_unsafe_query_rejected_before_network():
    with pytest.raises(MissionError, match="SEARCH_NOT_CONFIGURED"):
        SerpApiSearch("").search("battery", 1)
    with pytest.raises(MissionError, match="UNSAFE_QUERY"):
        SerpApiSearch("synthetic").search("mail me user@example.com", 1)
