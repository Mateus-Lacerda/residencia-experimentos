/** Barras em SVG próprio. Barra null aparece como "sem dado" hachurada, nunca como zero. */

import { useState } from "react";
import { useElementWidth } from "./useElementWidth.ts";
import { fmtCurto } from "../../utils/format.ts";

export interface Bar {
  label: string;
  value: number | null;
  /** marca barras com valor estimado (cobertura parcial) */
  estimated?: boolean;
  active?: boolean;
}

interface Props {
  bars: Bar[];
  formatValue: (v: number | null) => string;
  height?: number;
  onClick?: (i: number) => void;
}

const M = { top: 8, right: 6, bottom: 20, left: 46 };

export function BarChart({ bars, formatValue, height = 150, onClick }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const vals = bars.map((b) => b.value).filter((v): v is number => v != null);
  const hi = Math.max(1, ...vals) * 1.05;
  const iw = Math.max(0, width - M.left - M.right);
  const ih = height - M.top - M.bottom;
  const bw = bars.length ? iw / bars.length : 0;
  const y = (v: number) => M.top + ih - (v / hi) * ih;
  const passo = Math.max(1, Math.ceil(bars.length / 8));
  const h = hover != null ? bars[hover] : null;
  return (
    <div ref={ref} className="grafico">
      {width > 0 && (
        <svg width={width} height={height} onMouseLeave={() => setHover(null)}>
          <defs>
            <pattern id="hachura" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="5" height="5" fill="#e3e5e8" />
              <line x1="0" y1="0" x2="0" y2="5" stroke="#8a8f98" strokeWidth="1.5" />
            </pattern>
          </defs>
          {[0, hi / 2, hi].map((t, i) => (
            <g key={i}>
              <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} className="grafico-grade" />
              <text x={M.left - 6} y={y(t) + 4} textAnchor="end" className="grafico-eixo">
                {fmtCurto(t)}
              </text>
            </g>
          ))}
          {bars.map((b, i) => {
            const x = M.left + i * bw + bw * 0.12;
            const w = bw * 0.76;
            const vazio = b.value == null;
            const top = vazio ? M.top + ih * 0.55 : y(b.value!);
            return (
              <g
                key={i}
                onMouseEnter={() => setHover(i)}
                onClick={() => onClick?.(i)}
                style={{ cursor: onClick ? "pointer" : undefined }}
              >
                <rect x={M.left + i * bw} y={M.top} width={bw} height={ih} fill="transparent" />
                <rect
                  x={x}
                  y={top}
                  width={w}
                  height={M.top + ih - top}
                  fill={vazio ? "url(#hachura)" : b.active ? "#d6604d" : b.estimated ? "#9db8d6" : "#4b77a8"}
                  stroke={hover === i ? "#111418" : "none"}
                />
                {i % passo === 0 && (
                  <text x={x + w / 2} y={height - 6} textAnchor="middle" className="grafico-eixo">
                    {b.label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
      <div className="grafico-legenda">
        {h ? (
          <span>
            <span className="grafico-x">{h.label}</span> {formatValue(h.value)}
            {h.estimated ? " (estimado, cobertura parcial)" : ""}
          </span>
        ) : (
          <>
            <span><i style={{ background: "#4b77a8" }} /> observado</span>
            <span><i style={{ background: "#9db8d6" }} /> estimado (cobertura parcial)</span>
            <span><i className="hachura" /> sem dado</span>
          </>
        )}
      </div>
    </div>
  );
}
