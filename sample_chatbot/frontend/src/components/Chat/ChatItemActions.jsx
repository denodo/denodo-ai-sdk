import React from "react";
import PropTypes from "prop-types";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import CopyButton from "../CopyButton/CopyButton";

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
  copyText,
  onError,
}) => {
  const isError = Boolean(result && result.isError);

  const feedbackIcon = !isError && config.chatbot_feedback ? (
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

  const copyIcon = copyText ? (
    <CopyButton
      text={copyText}
      tooltipText={isError ? "Copy error" : "Copy response"}
      placement="left"
      container={resultsContainerRef && resultsContainerRef.current}
      className={isError ? "" : "ms-2"}
      onError={onError}
    />
  ) : null;

  const renderBaseIcon = () => {
    if (isError) return null;

    return (
      <OverlayTrigger
        placement="left"
        delay={{ show: 250, hide: 400 }}
        overlay={renderTooltip("AI")}
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
      {copyIcon}
      {feedbackIcon}
    </div>
  );
};

ChatItemActions.propTypes = {
  result: PropTypes.shape({
    isError: PropTypes.bool,
  }),
  config: PropTypes.shape({
    chatbot_feedback: PropTypes.bool,
  }),
  onOpenInfo: PropTypes.func,
  onFeedback: PropTypes.func,
  resultsContainerRef: PropTypes.object,
  copyText: PropTypes.string,
  onError: PropTypes.func,
};

export default ChatItemActions;
