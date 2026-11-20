import React from "react";
import PropTypes from "prop-types";

// Common layout of the in-place views of the DeepQuery Reports Manager:
// [← Back] [breadcrumb ................] [actions]
// followed by the scrollable content of the view.
const ReportPanelShell = ({ crumbs, onBack, actions, scroll, children }) => (
  <div className="rcp-panel">
    <div className="rcp-toolbar">
      <button type="button" className="rcp-back" onClick={onBack}>
        <i className="bi bi-arrow-left" />
        Back
      </button>
      <nav className="rcp-crumbs" aria-label="Breadcrumb">
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return (
            <React.Fragment key={`${crumb.label}-${index}`}>
              {index > 0 && <i className="bi bi-chevron-right rcp-crumb-sep" />}
              {isLast || !crumb.onClick ? (
                <span className={`rcp-crumb${isLast ? " rcp-crumb-current" : ""}`} title={crumb.label}>
                  {crumb.label}
                </span>
              ) : (
                <button type="button" className="rcp-crumb rcp-crumb-link" onClick={crumb.onClick} title={crumb.label}>
                  {crumb.label}
                </button>
              )}
            </React.Fragment>
          );
        })}
      </nav>
      {actions && <div className="rcp-actions">{actions}</div>}
    </div>
    <div className={`rcp-content${scroll ? " rcp-content-scroll" : ""}`}>{children}</div>
  </div>
);

ReportPanelShell.propTypes = {
  crumbs: PropTypes.arrayOf(
    PropTypes.shape({ label: PropTypes.string.isRequired, onClick: PropTypes.func })
  ).isRequired,
  onBack: PropTypes.func.isRequired,
  actions: PropTypes.node,
  scroll: PropTypes.bool,
  children: PropTypes.node,
};

export default ReportPanelShell;
