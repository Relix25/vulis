# vulis-obs-py

Observability helpers for Vulis services.

A thin wrapper around **OpenTelemetry** that:

- Configures a global tracer + meter provider (OTLP/gRPC exporter by default,
  no-op when no endpoint is configured — so importing a Vulis lib never
  crashes for lack of a collector).
- Stamps every span with Vulis semantic attributes:
  `vulis.service`, `vulis.surface`, `vulis.project_id`, `vulis.line_id`,
  `vulis.model_version`, `vulis.dataset_version`, ...
- Exposes a small set of **ready-made Vulis metrics** under the `vulis.*`
  namespace (counters + histograms) used by all services, so dashboards
  can rely on consistent instrument names.
- Provides a `meter()` decorator/context-manager for span creation.

## Quick usage

```python
from vulis_obs import init_observability, meter, counter, histogram, span_attrs

init_observability(service="dataset", endpoint="http://otel:4317")

with meter("dataset.import", attrs={"vulis.dataset_id": str(did)}):
    counter("vulis.dataset.samples_imported").add(n)
    histogram("vulis.dataset.import_seconds").record(elapsed)
```

## Metric reference (predefined)

| Name | Type | Unit | When to use |
|---|---|---|---|
| `vulis.dataset.samples_imported` | counter | 1 | After a dataset import |
| `vulis.model.approval_transitions` | counter | 1 | On a registry approval step |
| `vulis.serving.inferences` | counter | 1 | Per inference call |
| `vulis.serving.inference_seconds` | histogram | s | Inference latency |
| `vulis.serving.batch_size` | histogram | 1 | Inference batch size |
| `vulis.fleet.edge_heartbeat` | counter | 1 | On each received heartbeat |
| `vulis.storage.read_bytes` | counter | By | Bytes read from a backend |
| `vulis.storage.write_bytes` | counter | By | Bytes written to a backend |

## License

BSL 1.1 → AGPL-3.0 on 2030-06-14. See [../../LICENSE](../../LICENSE).
