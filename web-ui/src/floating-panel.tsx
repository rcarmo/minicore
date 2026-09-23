import type { ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";

type Point = { x: number; y: number };
export function FloatingPanel({
  title,
  children,
  kind = "routing",
  heading,
}: {
  title: string;
  children: ComponentChildren;
  kind?: "routing" | "inspector";
  heading?: ComponentChildren;
}) {
  const ref = useRef<HTMLElement>(null);
  const [position, setPosition] = useState<Point | null>(null);
  const [minimized, setMinimized] = useState(false);
  const drag = useRef<{ x: number; y: number; start: Point } | null>(null);
  const clamp = (point: Point) => {
    const box = ref.current?.getBoundingClientRect();
    return {
      x: Math.max(8, Math.min(point.x, innerWidth - (box?.width ?? 320) - 8)),
      y: Math.max(8, Math.min(point.y, innerHeight - (box?.height ?? 50) - 8)),
    };
  };
  useEffect(() => {
    const resize = () => setPosition((p) => (p ? clamp(p) : null));
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  useEffect(() => {
    setPosition((p) => (p ? clamp(p) : null));
  }, [minimized]);
  return (
    <section
      ref={ref}
      class={`floating-panel floating-${kind}`}
      aria-label={title}
      data-minimized={minimized}
      style={
        position
          ? { left: position.x, top: position.y, right: "auto", bottom: "auto" }
          : undefined
      }
    >
      <div class="floating-titlebar">
        <button
          class="panel-drag"
          aria-label={`Move ${title}`}
          title="Drag to move · arrow keys to reposition"
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            const box = ref.current!.getBoundingClientRect();
            drag.current = {
              x: e.clientX,
              y: e.clientY,
              start: { x: box.x, y: box.y },
            };
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => {
            const d = drag.current;
            if (d)
              setPosition(
                clamp({
                  x: d.start.x + e.clientX - d.x,
                  y: d.start.y + e.clientY - d.y,
                }),
              );
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
          onKeyDown={(e) => {
            const movement: Record<string, Point> = {
              ArrowLeft: { x: -24, y: 0 },
              ArrowRight: { x: 24, y: 0 },
              ArrowUp: { x: 0, y: -24 },
              ArrowDown: { x: 0, y: 24 },
            };
            const delta = movement[e.key];
            if (!delta) return;
            e.preventDefault();
            const box = ref.current!.getBoundingClientRect();
            setPosition(clamp({ x: box.x + delta.x, y: box.y + delta.y }));
          }}
        >
          <span aria-hidden="true">⠿</span> {title}
        </button>
        {heading}
        <button
          class="panel-minimize"
          aria-label={`${minimized ? "Restore" : "Minimize"} ${title}`}
          aria-expanded={!minimized}
          onClick={() => setMinimized((v) => !v)}
        >
          {minimized ? "+" : "−"}
        </button>
      </div>
      <div class="floating-body" hidden={minimized}>
        {children}
      </div>
    </section>
  );
}
