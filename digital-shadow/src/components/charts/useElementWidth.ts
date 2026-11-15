import { useCallback, useEffect, useRef, useState } from "react";

/** Largura do elemento, atualizada por ResizeObserver. */
export function useElementWidth<T extends HTMLElement>(): [(el: T | null) => void, number] {
  const [width, setWidth] = useState(0);
  const obs = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    obs.current?.disconnect();
    if (!el) return;
    setWidth(el.clientWidth);
    obs.current = new ResizeObserver(() => setWidth(el.clientWidth));
    obs.current.observe(el);
  }, []);
  useEffect(() => () => obs.current?.disconnect(), []);
  return [ref, width];
}
