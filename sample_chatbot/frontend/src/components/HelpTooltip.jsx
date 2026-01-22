import React from "react";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";

const HelpTooltip = ({ text, placement = "right" }) => {
  const renderTooltip = (props) => (
    <Tooltip id={`tooltip-${text.slice(0, 10)}`} {...props}>
      <div className="text-start" style={{ textAlign: 'left' }}>
        {text}
      </div>
    </Tooltip>
  );

  return (
    <OverlayTrigger
      placement={placement}
      delay={{ show: 250, hide: 400 }}
      overlay={renderTooltip}
    >
      <span
        style={{ cursor: "pointer", color: "#6c757d", fontSize: "1rem" }}
        aria-label="Help"
        className="d-inline-flex align-items-center"
      >
        <i className="bi bi-question-circle-fill"></i>
      </span>
    </OverlayTrigger>
  );
};

export default HelpTooltip;
