import React, { useState } from "react";
import PropTypes from "prop-types";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import "./CopyButton.css";

// Helper with fallback for insecure origins (http://0.0.0.0, local IPs, etc.)
const copyToClipboard = async (textToCopy) => {
  if (typeof navigator !== "undefined" && navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(textToCopy);
      return;
    } catch (err) {
      console.warn("navigator.clipboard.writeText failed, trying fallback:", err);
    }
  }

  let textArea = null;
  try {
    textArea = document.createElement("textarea");
    textArea.value = textToCopy;
    textArea.style.position = "fixed";
    textArea.style.top = "0";
    textArea.style.left = "-9999px";
    textArea.style.width = "2em";
    textArea.style.height = "2em";
    textArea.style.padding = "0";
    textArea.style.border = "none";
    textArea.style.outline = "none";
    textArea.style.boxShadow = "none";
    textArea.style.background = "transparent";
    textArea.style.opacity = "0";
    textArea.setAttribute("readonly", "");

    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    const successful = document.execCommand("copy");
    if (!successful) {
      throw new Error("document.execCommand('copy') returned false");
    }
  } catch (err) {
    throw new Error(err?.message || "Could not copy text to clipboard.");
  } finally {
    if (textArea && textArea.parentNode) {
      textArea.parentNode.removeChild(textArea);
    }
  }
};

const CopyButton = ({
  text,
  tooltipText = "Copy to clipboard",
  copiedTooltipText = "Copied!",
  placement = "top",
  container = null,
  className = "",
  onError = null,
  errorMessage = "Unable to copy to clipboard. Clipboard permissions may be blocked or the connection is not secure (HTTP/0.0.0.0).",
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e) => {
    e.stopPropagation();
    if (!text) return;

    try {
      await copyToClipboard(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Error copying to clipboard:", err);
      if (typeof onError === "function") {
        onError(errorMessage);
      }
    }
  };

  const renderTooltip = (props) => (
    <Tooltip id="copy-btn-tooltip" {...props}>
      {copied ? copiedTooltipText : tooltipText}
    </Tooltip>
  );

  return (
    <OverlayTrigger
      placement={placement}
      delay={{ show: 200, hide: 300 }}
      overlay={renderTooltip}
      container={container}
    >
      <button
        type="button"
        className={`copy-button ${copied ? "is-copied" : ""} ${className}`}
        onClick={handleCopy}
        aria-label={copied ? copiedTooltipText : tooltipText}
      >
        <i className={`bi bi-${copied ? "check-lg text-success" : "copy"}`} />
      </button>
    </OverlayTrigger>
  );
};

CopyButton.propTypes = {
  text: PropTypes.string,
  tooltipText: PropTypes.string,
  copiedTooltipText: PropTypes.string,
  placement: PropTypes.string,
  container: PropTypes.any,
  className: PropTypes.string,
  onError: PropTypes.func,
  errorMessage: PropTypes.string,
};

export default CopyButton;
