import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { buildViewCatalogUrl } from "../../utils/viewUrl";
import CustomTooltip from "../CustomTooltip/CustomTooltip";
import { formatTokenCount } from "./ContextUsageIndicator";
import "./ContextUsageIndicator.css";

const assetBaseUrl = import.meta.env.BASE_URL;
const MORE_CHIP_WIDTH = 96;

function viewLabel(name) {
  return String(name || "").replace(/"/g, "");
}

export const ViewChip = ({ view, dataCatalogUrl, showHint = true, used = false }) => {
  const label = viewLabel(view.name);
  const catalogUrl = buildViewCatalogUrl(dataCatalogUrl, view.name);
  const chipClassName = used ? "context-view-chip context-view-chip-used" : "context-view-chip";
  const content = (
    <>
      <img src={`${assetBaseUrl}denodo_view.svg`} alt="" width="14" height="14" />
      <span className="context-view-name">{label}</span>
      {!!view.tokens && (
        <span className="context-view-tokens">
          {formatTokenCount(view.tokens)} tokens
        </span>
      )}
    </>
  );

  const chip = catalogUrl ? (
    <a
      data-view-chip
      href={catalogUrl}
      target="_blank"
      rel="noopener noreferrer"
      className={chipClassName}
    >
      {content}
    </a>
  ) : (
    <span data-view-chip className={chipClassName}>
      {content}
    </span>
  );

  if (!showHint) return chip;

  return (
    <CustomTooltip
      id={`context-view-${label.replace(/[^A-Za-z0-9_-]/g, "-")}`}
      placement="top"
      tooltipClassName="custom-tooltip-wide"
      content={
        <>
          The view <code>{label}</code> is in the current agent's context window.
          This means that its metadata can be used by the agent to answer questions.{" "}
          {!!view.tokens && (
            <>Its metadata uses about {formatTokenCount(view.tokens)} tokens of the
            context window.{" "}</>
          )}
          New views will appear here automatically when the agent
          discovers them through the <code>metadata_search</code> tool.
        </>
      }
    >
      {chip}
    </CustomTooltip>
  );
};

const ContextViewsRow = ({ views, dataCatalogUrl }) => {
  const rowRef = useRef(null);
  const measureRef = useRef(null);
  const moreRef = useRef(null);
  const [visibleCount, setVisibleCount] = useState(views ? views.length : 0);
  const [moreOpen, setMoreOpen] = useState(false);

  useLayoutEffect(() => {
    const row = rowRef.current;
    const measure = measureRef.current;
    if (!row || !measure || !views || views.length === 0) return undefined;

    const fit = () => {
      const chips = Array.from(measure.querySelectorAll("[data-view-chip]"));
      const available = row.clientWidth;
      let used = 0;
      let count = 0;
      for (let index = 0; index < chips.length; index += 1) {
        const width = chips[index].offsetWidth + 8;
        const moreRemain = chips.length - (index + 1) > 0;
        const reserve = moreRemain ? MORE_CHIP_WIDTH : 0;
        if (count > 0 && used + width + reserve > available) break;
        used += width;
        count += 1;
      }
      setVisibleCount(Math.max(count, 1));
    };

    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(row);
    return () => observer.disconnect();
  }, [views]);

  useEffect(() => {
    if (!moreOpen) return undefined;
    const onPointerDown = (event) => {
      if (moreRef.current && !moreRef.current.contains(event.target)) {
        setMoreOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setMoreOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [moreOpen]);

  if (!views || views.length === 0) return null;

  const shown = views.slice(0, visibleCount);
  const hidden = views.slice(visibleCount);

  return (
    <div className="context-views">
      <div className="context-views-measure" ref={measureRef} aria-hidden="true">
        {views.map((view) => (
          <ViewChip key={`measure-${view.name}`} view={view} dataCatalogUrl={dataCatalogUrl} showHint={false} />
        ))}
      </div>
      <div className="context-views-row" ref={rowRef}>
        {shown.map((view) => (
          <ViewChip key={view.name} view={view} dataCatalogUrl={dataCatalogUrl} />
        ))}
        {hidden.length > 0 && (
          <div className="context-views-more" ref={moreRef}>
            {moreOpen && (
              <div className="context-views-popover" role="dialog" aria-label="More views in context">
                {hidden.map((view) => (
                  <ViewChip key={view.name} view={view} dataCatalogUrl={dataCatalogUrl} />
                ))}
              </div>
            )}
            <button
              type="button"
              className="context-view-more-chip"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((current) => !current)}
            >
              +{hidden.length} views
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ContextViewsRow;
