import React from "react";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";

const assetBaseUrl = import.meta.env.BASE_URL;

const renderTooltip = (content) => (
  <Tooltip id="chat-item-action-tooltip">{content}</Tooltip>
);

const ChatItemActions = ({
  result,
  config,
  onOpenInfo,
  onFeedback,
  resultsContainerRef,
}) => {
  const tooltipText = result && result.isError ? "View error details" : "AI";

  const feedbackIcon = config.chatbot_feedback ? (
    <OverlayTrigger
      placement="left"
      delay={{ show: 250, hide: 400 }}
      overlay={renderTooltip("Provide feedback")}
      container={resultsContainerRef && resultsContainerRef.current}
    >
      <img
        src={`${assetBaseUrl}feedback.svg`}
        alt="Feedback"
        width="20"
        height="20"
        className="ms-2 cursor-pointer"
        onClick={onFeedback}
      />
    </OverlayTrigger>
  ) : null;

  const renderBaseIcon = () => {
    // Always show AI icon as requested for the parent result object
    return (
      <OverlayTrigger
        placement="left"
        delay={{ show: 250, hide: 400 }}
        overlay={renderTooltip(tooltipText)}
        container={resultsContainerRef && resultsContainerRef.current}
      >
        <img
          src={`${assetBaseUrl}ai.png`}
          alt="AI Icon"
          width="20"
          height="20"
          className="cursor-pointer"
          onClick={onOpenInfo}
        />
      </OverlayTrigger>
    );
  };

  return (
    <div className="d-flex flex-row align-items-center position-relative">
      {renderBaseIcon()}
      {feedbackIcon}
    </div>
  );
};

export default ChatItemActions;
