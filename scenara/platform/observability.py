from __future__ import annotations

from collections import defaultdict
from threading import Lock

HISTOGRAM_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_seconds_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._duration_seconds_count: dict[tuple[str, str], int] = defaultdict(int)
        self._duration_seconds_buckets: dict[tuple[str, str, float], int] = defaultdict(int)

    def observe(self, method: str, route: str, status_code: int, duration_seconds: float) -> None:
        method = method.upper()
        duration_seconds = max(0.0, duration_seconds)
        with self._lock:
            self._requests[(method, route, status_code)] += 1
            self._duration_seconds_sum[(method, route)] += duration_seconds
            self._duration_seconds_count[(method, route)] += 1
            for upper_bound in HISTOGRAM_BUCKETS:
                if duration_seconds <= upper_bound:
                    self._duration_seconds_buckets[(method, route, upper_bound)] += 1

    def render(self) -> str:
        lines = [
            "# HELP scenara_http_requests_total HTTP requests handled by Scenara.",
            "# TYPE scenara_http_requests_total counter",
        ]
        with self._lock:
            request_rows = sorted(self._requests.items())
            duration_sums = dict(self._duration_seconds_sum)
            duration_counts = dict(self._duration_seconds_count)
            duration_buckets = dict(self._duration_seconds_buckets)
        for (method, route, status_code), count in request_rows:
            lines.append(
                f'scenara_http_requests_total{{method="{_label(method)}",route="{_label(route)}",'
                f'status="{status_code}"}} {count}'
            )
        lines.extend(
            (
                "# HELP scenara_http_request_duration_seconds HTTP request duration.",
                "# TYPE scenara_http_request_duration_seconds histogram",
            )
        )
        for method, route in sorted(duration_counts):
            labels = f'method="{_label(method)}",route="{_label(route)}"'
            for upper_bound in HISTOGRAM_BUCKETS:
                count = duration_buckets.get((method, route, upper_bound), 0)
                lines.append(
                    f'scenara_http_request_duration_seconds_bucket{{{labels},le="{upper_bound:g}"}} {count}'
                )
            count = duration_counts[(method, route)]
            lines.append(f'scenara_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {count}')
            lines.append(
                f"scenara_http_request_duration_seconds_sum{{{labels}}} "
                f"{duration_sums[(method, route)]:.9f}"
            )
            lines.append(f"scenara_http_request_duration_seconds_count{{{labels}}} {count}")
        return "\n".join(lines) + "\n"


__all__ = ["RequestMetrics"]
