import { useEffect, useState } from "react";
import { analyzeVariants, type Variant, type VariantReport } from "../api";
import { formatDuration } from "../format";

interface Props {
  logId: string;
  selectedRank: number | null;
  onSelect: (variant: Variant | null) => void;
}

export default function VariantsPanel({ logId, selectedRank, onSelect }: Props) {
  const [report, setReport] = useState<VariantReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [topN, setTopN] = useState(10);
  const [minFreq, setMinFreq] = useState(1);

  useEffect(() => {
    let active = true;
    analyzeVariants(logId, { top_n: topN, min_frequency: minFreq })
      .then((r) => {
        if (active) setReport(r);
      })
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [logId, topN, minFreq]);

  return (
    <div className="side-panel">
      <div className="side-panel__head">
        <h3>Variants</h3>
        {report && (
          <span className="muted">
            {report.variant_count} distinct · {report.case_count} cases
          </span>
        )}
      </div>

      <div className="side-filters">
        <label>
          Top-N {topN}
          <input
            type="range"
            min={1}
            max={50}
            value={topN}
            onChange={(e) => setTopN(Number(e.target.value))}
          />
        </label>
        <label>
          Min freq {minFreq}
          <input
            type="range"
            min={1}
            max={20}
            value={minFreq}
            onChange={(e) => setMinFreq(Number(e.target.value))}
          />
        </label>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="variant-list">
        {report?.variants.map((v) => (
          <button
            key={v.rank}
            className={`variant-row${selectedRank === v.rank ? " selected" : ""}`}
            onClick={() => onSelect(selectedRank === v.rank ? null : v)}
          >
            <div className="variant-row__head">
              <span className="variant-row__rank">#{v.rank}</span>
              <span className="variant-row__pct">{v.percentage.toFixed(1)}%</span>
            </div>
            <div className="variant-row__bar">
              <span style={{ width: `${v.percentage}%` }} />
            </div>
            <div className="variant-row__seq">{v.sequence.join(" → ")}</div>
            <div className="variant-row__meta muted">
              {v.case_count} cases · ⏱ {formatDuration(v.avg_throughput_seconds)}
            </div>
          </button>
        ))}
        {report && report.variants.length === 0 && (
          <p className="muted">No variants match the current filters.</p>
        )}
      </div>
    </div>
  );
}
