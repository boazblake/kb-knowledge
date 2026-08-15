"""OpenTelemetry production wiring and safe component instrumentation."""
from __future__ import annotations

import os
from contextlib import nullcontext
from typing import Any, Mapping


class TelemetryUnavailable(RuntimeError):
    pass


SAFE_ATTRIBUTES = frozenset({
    "service.name", "component", "operation", "tenant", "workload",
    "connector", "workflow_id", "activity_type", "outcome", "retryable",
    "attempt", "status", "error.type",
})
_SECRET = ("token", "secret", "password", "authorization", "credential", "key")


def safe_attributes(attributes: Mapping[str, Any]) -> dict[str, str | int | bool]:
    """Allow only low-cardinality fields; never emit payloads or credentials."""
    result: dict[str, str | int | bool] = {}
    for key, value in attributes.items():
        key = str(key)
        if key not in SAFE_ATTRIBUTES or any(part in key.casefold() for part in _SECRET):
            continue
        if isinstance(value, (str, int, bool)):
            result[key] = value
    return result


class OpenTelemetry:
    """Real SDK + OTLP HTTP exporter. No in-process production fallback."""
    test_only = False

    def __init__(self, service_name: str, endpoint: str, *, tracer_provider=None,
                 meter_provider=None, install: bool = True):
        if not service_name or not endpoint:
            raise ValueError("telemetry service_name and endpoint required")
        if os.getenv("KB_PIPELINE_MODE", "").casefold() == "production" and not endpoint.startswith(("http://", "https://")):
            raise ValueError("production OTLP endpoint must be HTTP(S)")
        try:
            from opentelemetry import metrics, trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        except ImportError as exc:
            raise TelemetryUnavailable("OpenTelemetry SDK and OTLP HTTP exporter required") from exc
        if install and tracer_provider is None:
            resource = Resource.create({"service.name": service_name})
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")))
            trace.set_tracer_provider(tracer_provider)
        if install and meter_provider is None:
            resource = Resource.create({"service.name": service_name})
            reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{endpoint.rstrip('/')}/v1/metrics"))
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
        self.tracer = trace.get_tracer(service_name, tracer_provider=tracer_provider)
        self.meter = metrics.get_meter(service_name, meter_provider=meter_provider)
        self._counters: dict[str, Any] = {}

    def span(self, name: str, **attributes: Any):
        return self.tracer.start_as_current_span(name, attributes=safe_attributes(attributes))

    def counter(self, name: str, value: int = 1, **attributes: Any) -> None:
        counter = self._counters.setdefault(name, self.meter.create_counter(name))
        counter.add(value, safe_attributes(attributes))


def span(telemetry: Any, name: str, **attributes: Any):
    return telemetry.span(name, **attributes) if telemetry else nullcontext()
