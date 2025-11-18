# Chronos Fragment Output Specification

The LLM normalization layer must emit **valid JSON** describing one or more `SeriesFragment` objects. Use the following schema exactly—every key is lower case snake_case and values must match the expected types. When information is unavailable, use `null` (do **not** omit required keys).

## Fragment object

```json
{
  "chunk_id": "string",
  "series_id": "string",
  "summary": "optional string (<=512 chars) or null",
  "frequency": "optional pandas-style freq alias (e.g. \"1d\", \"1h\") or null",
  "target": {
    "values": [[history numbers ...] or [univariate numbers ...]],
    "timestamps": ["ISO-8601 strings"],    // optional, same length as values
    "units": "optional string or null",
    "scale_factor": number or null,
    "normalized": true/false or null
  },
  "past_covariates": {
    "name": {
      "values": [history numbers ...],     // length must equal target history length
      "timestamps": ["optional timestamps"],   // if provided length must match values
      "type": "continuous" or "categorical",
      "units": "optional string or null",
      "scale_factor": number or null
    }
    // additional covariates ...
  },
  "future_covariates": {
    "name": {
      "values": [future horizon numbers ...],  // length == requested prediction horizon
      "timestamps": ["optional timestamps"]    // optional but if present must match values
    }
    // keys here must also appear in past_covariates
  },
  "issues": ["optional list of warning strings"],
  "confidence": 0.0-1.0                      // optional, defaults to 0.5 if absent
}
```

### Rules

1. `chunk_id` uniquely identifies the source chunk (e.g., `"pdf_chunk#3"`).  
2. `series_id` groups fragments belonging to the same logical time series; reuse the same value across chunks.  
3. `target.values`:
   - For **univariate** series use a flat array: `[1.0, 2.0, ...]`.  
   - For **multivariate** series provide a nested array: `[[var1...], [var2...]]`. All variates must share the same history length.  
4. If `future_covariates` is present, each key **must** already exist in `past_covariates` and its horizon length must equal the requested prediction horizon supplied to the agent.  
5. Use numeric types for all arrays (no strings) except categorical covariates, which may contain strings but must be consistent across past and future arrays.  
6. Provide timestamps as ISO-8601 strings (`"YYYY-MM-DDTHH:MM:SS"`). When timestamps are missing or irregular, set the field to `null` and make a note in `issues`.  
7. `confidence` reflects how reliable the extraction is (0.0–1.0). When uncertain, choose a conservative value (e.g., 0.4).  
8. Every fragment should capture origin issues via `issues` (missing values, inferred frequency, etc.) so the orchestrator can surface them later.
9. `summary` must be a short, human-readable sentence that mentions the target, key covariates, intent (forecasting goal), and data provenance if relevant (e.g., “OCR from chart”, “derived from public CSV”).

## Example (univariate with future covariates)

```json
[
  {
    "chunk_id": "csv_chunk#1",
    "series_id": "ticker:AAPL",
    "summary": "Daily close price with volume covariate.",
    "frequency": "1d",
    "target": {
      "values": [189.23, 190.01, 188.77],
      "timestamps": ["2024-07-01T00:00:00", "2024-07-02T00:00:00", "2024-07-03T00:00:00"],
      "units": "USD",
      "scale_factor": 1.0,
      "normalized": false
    },
    "past_covariates": {
      "volume": {
        "values": [51230000, 49821000, 54310000],
        "type": "continuous",
        "units": "shares",
        "scale_factor": 1.0
      }
    },
    "future_covariates": {
      "volume": {
        "values": [52000000, 52500000],
        "timestamps": ["2024-07-04T00:00:00", "2024-07-05T00:00:00"]
      }
    },
    "issues": [],
    "confidence": 0.85
  }
]
```

## Example (multivariate without explicit timestamps)

```json
[
  {
    "chunk_id": "image_chunk#2",
    "series_id": "energy:metropolis",
    "summary": "Two-zone power consumption extracted from chart image. Frequency inferred as hourly.",
    "frequency": "1h",
    "target": {
      "values": [
        [120.4, 121.9, 124.1, 126.0],
        [98.2,  99.0,  101.5, 102.3]
      ],
      "timestamps": null,
      "units": "MW",
      "scale_factor": 1.0,
      "normalized": false
    },
    "past_covariates": {
      "temperature": {
        "values": [29.1, 29.5, 30.0, 30.4],
        "type": "continuous",
        "units": "Celsius"
      },
      "holiday_flag": {
        "values": ["none", "none", "none", "none"],
        "type": "categorical"
      }
    },
    "future_covariates": {},
    "issues": ["Timestamps approximated from chart; frequency inferred as hourly."],
    "confidence": 0.6
  }
]
```

Return **only** the JSON array (no prose, code fences, or explanations). The orchestration layer will parse the output and handle validation.

