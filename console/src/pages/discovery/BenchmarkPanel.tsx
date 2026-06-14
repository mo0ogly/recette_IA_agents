/**
 * Benchmark panel: judge accuracy per dimension, per style, per area.
 *
 * Renders GET /subjects/benchmark -- the AF Labs-style metrics beyond pass/fail.
 * Read-only; the backend is deterministic (I4). Reuses the discovery table
 * styling -- no new CSS.
 */

import { useEffect, useState } from "react";
import { getBenchmark } from "../../api/client";
import type { Benchmark, BenchmarkArea } from "../../api/client";

const DIMS = ["identity", "capabilities", "policy", "behavior"] as const;

function AccCells({ area }: { area: BenchmarkArea }): JSX.Element {
  return (
    <>
      {DIMS.map((d) => (
        <td key={d} className={area.dimension_accuracy[d] >= 1 ? "ok" : "fail"}>
          {(area.dimension_accuracy[d] * 100).toFixed(0)}%
        </td>
      ))}
    </>
  );
}

export default function BenchmarkPanel(): JSX.Element {
  const [bench, setBench] = useState<Benchmark | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getBenchmark()
      .then((b) => alive && setBench(b))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  if (error) {
    return (
      <div className="discovery-error" role="alert" data-testid="benchmark-error">
        {error}
      </div>
    );
  }
  if (!bench) return <p className="discovery-loading">Loading benchmark...</p>;

  const areas: [string, BenchmarkArea][] = [
    ["identification", bench.identification],
    ["maf", bench.maf],
    ["orchestration", bench.orchestration],
  ];

  return (
    <section data-testid="benchmark">
      <h2>Benchmark — judge accuracy</h2>
      <table className="discovery-table">
        <thead>
          <tr>
            <th>Area / style</th>
            <th>Passed</th>
            {DIMS.map((d) => (
              <th key={d}>{d.slice(0, 4)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {areas.map(([name, area]) => (
            <tr key={name} data-testid={`benchmark-area-${name}`}>
              <td>{name}</td>
              <td>
                {area.passed}/{area.total}
              </td>
              <AccCells area={area} />
            </tr>
          ))}
          {Object.entries(bench.orchestration.by_style).map(([style, area]) => (
            <tr key={style} data-testid={`benchmark-style-${style}`}>
              <td>&nbsp;&nbsp;{style}</td>
              <td>
                {area.passed}/{area.total}
              </td>
              <AccCells area={area} />
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
