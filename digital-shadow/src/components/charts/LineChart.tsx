/**
 * Gráfico de linhas em SVG próprio. Valores null interrompem a linha (lacuna visível),
 * nunca são desenhados como zero.
 */

import { useMemo, useState } from "react";
import { useElementWidth } from "./useElementWidth.ts";
import { fmtCurto } from "../../utils/format.ts";

export interface Series {
  label: string;
  color: string;
  values: (number | null)[];
  dashed?: boolean;
}

interface Props {
  series: Series[];
  xLabel: (i: number) => string;
  formatValue: (v: number | null) => string;
  height?: number;
  /** faixa de índices destacada (ex.: período selecionado dentro do histórico) */
  highlight?: { start: number; end: number } | null;
  emptyMessage?: string;
}

const M = { top: 10, right: 10, bottom: 22, left: 46 };

function buildPath(values: (number | null)[], x: (i: number) => number, y: (v: number) => number): string {
  let d = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v == null || !Number.isFinite(v)) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  return d;
}

export function LineChart({ series, xLabel, formatValue, height = 170, highlight, emptyMessage }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const n = Math.max(0, ...series.map((s) => s.values.length));
  const valid = series.flatMap((s) => s.values.filter((v): v is number => v != null && Number.isFinite(v)));

  const geo = useMemo(() => {
    if (valid.length === 0 || n === 0 || width === 0) return null;
    let lo = Math.min(0, ...valid);
    let hi = Math.max(...valid);
    if (hi <= lo) hi = lo + 1;
    const pad = (hi - lo) * 0.05;
    hi += pad;
    if (lo < 0) lo -= pad;
    const iw = width - M.left - M.right;
    const ih = height - M.top - M.bottom;
    const x = (i: number) => M.left + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
    const y = (v: number) => M.top + ih - ((v - lo) / (hi - lo)) * ih;
    const ticks = [lo, lo + (hi - lo) / 2, hi];
    return { x, y, ticks, iw, ih };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series, width, height, n]);

  if (valid.length === 0) {
    return (
      <div ref={ref} className="grafico-vazio" style={{ height }}>
        {emptyMessage ?? "Sem leituras no período"}
      </div>
    );
  }

  const xTicks = n > 1 ? [0, Math.floor((n - 1) / 2), n - 1] : [0];
  return (
    <div ref={ref} className="grafico">
      {geo && (
        <svg
          width={width}
          height={height}
          onMouseMove={(e) => {
            const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
            const t = (e.clientX - r.left - M.left) / geo.iw;
            setHover(Math.max(0, Math.min(n - 1, Math.round(t * (n - 1)))));
          }}
          onMouseLeave={() => setHover(null)}
        >
          {highlight && (
            <rect
              x={geo.x(highlight.start)}
              y={M.top}
              width={Math.max(2, geo.x(highlight.end) - geo.x(highlight.start))}
              height={geo.ih}
              className="grafico-destaque"
            />
          )}
          {geo.ticks.map((t, i) => (
            <g key={i}>
              <line x1={M.left} x2={width - M.right} y1={geo.y(t)} y2={geo.y(t)} className="grafico-grade" />
              <text x={M.left - 6} y={geo.y(t) + 4} textAnchor="end" className="grafico-eixo">
                {fmtCurto(t)}
              </text>
            </g>
          ))}
          {xTicks.map((i, k) => (
            <text
              key={i}
              x={geo.x(i)}
              y={height - 6}
              textAnchor={k === 0 ? "start" : k === xTicks.length - 1 ? "end" : "middle"}
              className="grafico-eixo"
            >
              {xLabel(i)}
            </text>
          ))}
          {series.map((s) => (
            <path
              key={s.label}
              d={buildPath(s.values, geo.x, geo.y)}
              fill="none"
              stroke={s.color}
              strokeWidth={1.4}
              strokeDasharray={s.dashed ? "4 3" : undefined}
            />
          ))}
          {hover != null && (
            <line x1={geo.x(hover)} x2={geo.x(hover)} y1={M.top} y2={M.top + geo.ih} className="grafico-cursor" />
          )}
        </svg>
      )}
      <div className="grafico-legenda">
        {hover != null ? (
          <>
            <span className="grafico-x">{xLabel(hover)}</span>
            {series.map((s) => (
              <span key={s.label}>
                <i style={{ background: s.color }} /> {s.label}: {formatValue(s.values[hover] ?? null)}
              </span>
            ))}
          </>
        ) : (
          series.map((s) => (
            <span key={s.label}>
              <i style={{ background: s.color }} /> {s.label}
            </span>
          ))
        )}
      </div>
    </div>
  );
}
