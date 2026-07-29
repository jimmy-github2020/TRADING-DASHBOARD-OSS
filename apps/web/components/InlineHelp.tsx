"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

type InlineHelpProps = {
  label: string;
  content: ReactNode;
  placement?: "top" | "right" | "bottom" | "left";
  size?: "default" | "large";
  maxWidth?: number;
};

export function InlineHelp({
  label,
  content,
  placement = "bottom",
  size = "default",
  maxWidth = 320
}: InlineHelpProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <span className={`inline-help ${open ? "open" : ""} ${placement}`} ref={rootRef}>
      <button
        aria-controls={id}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        aria-label={label}
        className={`inline-help-button ${size}`}
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        ?
      </button>
      {open ? (
        <span className="inline-help-popover" id={id} role="tooltip" style={{ maxWidth }}>
          {content}
        </span>
      ) : null}
    </span>
  );
}
