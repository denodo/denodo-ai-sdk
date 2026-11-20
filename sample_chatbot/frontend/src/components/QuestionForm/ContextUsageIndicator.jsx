import React, { useEffect, useRef, useState } from "react";
import "./ContextUsageIndicator.css";

const SEGMENT_COLORS = {
  conversation: "#3b82f6",
  views: "#8b5cf6",
  tools: "#f97316",
  skills: "#22c55e",
  system_prompt: "#eab308",
};

const RING_RADIUS = 7;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

function trimDecimal(value) {
  const fixed = value.toFixed(1);
  return fixed.endsWith(".0") ? String(Math.round(value)) : fixed;
}

export function formatTokenCount(value) {
  const n = Number(value) || 0;
  if (n >= 1000000) {
    const millions = n / 1000000;
    return `${millions >= 10 ? Math.round(millions) : trimDecimal(millions)}M`;
  }
  if (n >= 1000) {
    const thousands = n / 1000;
    return `${thousands >= 100 ? Math.round(thousands) : trimDecimal(thousands)}k`;
  }
  return String(Math.round(n));
}

function estimateTokens(text) {
  if (!text || !text.trim()) return 0;
  return Math.ceil(text.length / 4);
}

function withDraft(usage, draftText) {
  if (!usage) return null;
  const draftTokens = estimateTokens(draftText);
  if (!draftTokens) return { ...usage, draftTokens: 0 };
  const segments = (usage.segments || []).map((segment) => (
    segment.id === "conversation"
      ? { ...segment, tokens: segment.tokens + draftTokens }
      : segment
  ));
  return {
    ...usage,
    used: (usage.used || 0) + draftTokens,
    segments,
    draftTokens,
  };
}

function ringColor(percent) {
  if (percent >= 90) return "#dc3545";
  if (percent >= 70) return "#d97706";
  return "#112533";
}

const ContextUsageIndicator = ({ usage, draftText }) => {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const display = withDraft(usage, draftText);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const windowTokens = display?.context_window || 0;
  const limitTokens = display?.input_budget || windowTokens;
  const usedTokens = display?.used || 0;
  const percent = windowTokens ? (usedTokens / windowTokens) * 100 : 0;
  const fill = Math.min(percent, 100);
  const dash = (fill / 100) * RING_CIRCUMFERENCE;
  const overLimit = limitTokens > 0 && usedTokens > limitTokens;
  const segments = display?.segments || [];
  const label = display ? `Context ${Math.round(percent)}%` : "Context";

  return (
    <div className="context-usage" ref={rootRef}>
      {open && (
        <div className="context-usage-panel" role="dialog" aria-label="Context window">
          <div className="context-usage-kicker">Context window</div>
          <div className="context-usage-percent">{display ? `${Math.round(percent)}%` : "…"}</div>
          <div className="context-usage-total">
            {display
              ? `${formatTokenCount(usedTokens)} / ${formatTokenCount(windowTokens)}`
              : "Loading…"}
          </div>

          <div className="context-usage-bar" aria-hidden="true">
            {windowTokens > 0 && segments.map((segment) => (
              segment.tokens > 0 && (
                <span
                  key={segment.id}
                  style={{
                    width: `${Math.min((segment.tokens / windowTokens) * 100, 100)}%`,
                    backgroundColor: SEGMENT_COLORS[segment.id] || "#9ca3af",
                  }}
                />
              )
            ))}
          </div>

          <ul className="context-usage-legend">
            {segments.map((segment) => {
              const share = windowTokens ? (segment.tokens / windowTokens) * 100 : 0;
              return (
                <li key={segment.id}>
                  <span className="context-usage-swatch" style={{ backgroundColor: SEGMENT_COLORS[segment.id] }} />
                  <span className="context-usage-label">
                    {segment.label}
                    {segment.id === "conversation" && display.draftTokens > 0 ? "*" : ""}
                  </span>
                  <span className="context-usage-figures">
                    <span>{formatTokenCount(segment.tokens)}</span>
                    <span className="context-usage-share">{share.toFixed(1)}%</span>
                  </span>
                </li>
              );
            })}
            <li>
              <span className="context-usage-swatch context-usage-swatch-free" />
              <span className="context-usage-label">Free space</span>
              <span className="context-usage-figures">
                <span>{formatTokenCount(Math.max(windowTokens - usedTokens, 0))}</span>
                <span className="context-usage-share">
                  {windowTokens ? Math.max(100 - percent, 0).toFixed(1) : "0.0"}%
                </span>
              </span>
            </li>
          </ul>

          {overLimit && (
            <p className="context-usage-note">
              {display.draftTokens > 0
                ? "Sending this message would go past the context window. Older question and answer pairs will be trimmed to the last "
                : "The latest question and answer are still over the context window after older turns were left out. The keep budget is "}
              {formatTokenCount(display.keep_tokens || 30000)} tokens.
            </p>
          )}
          {!overLimit && display?.will_compact && (
            <p className="context-usage-note">
              Older turns are left out of the next request so it stays inside the context window.
            </p>
          )}
          {display?.draftTokens > 0 && (
            <p className="context-usage-footnote">
              * The unsent message is included as an estimate.
            </p>
          )}
          <p className="context-usage-estimate">
            Token count is estimated and may not be 100% accurate.
          </p>
        </div>
      )}

      <button
        type="button"
        className="context-usage-pill"
        aria-expanded={open}
        aria-label="Context window usage"
        onClick={() => setOpen((current) => !current)}
      >
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
          <circle cx="9" cy="9" r={RING_RADIUS} fill="none" stroke="#e5e7eb" strokeWidth="2" />
          <circle
            cx="9"
            cy="9"
            r={RING_RADIUS}
            fill="none"
            stroke={ringColor(percent)}
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${RING_CIRCUMFERENCE}`}
            transform="rotate(-90 9 9)"
          />
        </svg>
        {label}
      </button>
    </div>
  );
};

export default ContextUsageIndicator;
