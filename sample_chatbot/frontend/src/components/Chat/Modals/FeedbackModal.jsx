import React, { useState } from "react";
import Form from "react-bootstrap/Form";
import { BaseModal } from "../../Common/Modal";
import { actionTypes } from "../../../reducers/chatReducer";
import { buildApiUrl } from "../../../api/client";
import CustomTooltip from "../../CustomTooltip/CustomTooltip";

const FeedbackModal = ({ 
  show, 
  onClose, 
  result, 
  dispatch, 
  resultIndex, 
  feedbackEnabled,
  onShowToast
}) => {
  const [feedbackValue, setFeedbackValue] = useState("");
  const [feedbackDetails, setFeedbackDetails] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!feedbackEnabled || !result) return null;

  const handleSubmit = async () => {
    if (!result.uuid) return;

    setSubmitting(true);

    try {
      const response = await fetch(buildApiUrl("submit_feedback"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          uuid: result.uuid,
          feedback_value: feedbackValue,
          feedback_details: feedbackDetails,
        }),
      });

      let data = {};
      try {
        data = await response.json();
      } catch {
        data = {
          message: `The server returned an invalid response (HTTP ${response.status}).`,
        };
      }

      if (response.ok) {
        dispatch({
            type: actionTypes.SET_CHAT_ITEM_FEEDBACK,
            payload: { resultIndex, feedback: feedbackValue, feedbackDetails }
        });
        
        if (onShowToast) {
          onShowToast({
            show: true,
            title: "Feedback Submitted",
            message: "Thank you for your feedback.",
            variant: "success"
          });
        }
        
        onClose();
      } else {
        if (data.error === "uuid_not_found") {
          if (onShowToast) {
            onShowToast({
              show: true,
              title: "Feedback Not Saved",
              message: "This conversation is too old and its original record has been deleted to save space. Your feedback could not be saved.",
              variant: "warning"
            });
          }
          onClose();
        } else {
          const detail = data.message || `Feedback could not be saved (HTTP ${response.status}).`;
          if (onShowToast) {
            onShowToast({
              show: true,
              title: "Error",
              message: detail,
              variant: "danger"
            });
          } else {
            alert(detail);
          }
        }
      }
    } catch (error) {
      console.error("Error submitting feedback:", error);
      const detail =
        error?.message ||
        "Unable to reach the server. Check your connection and try again.";
      
      if (onShowToast) {
        onShowToast({
          show: true,
          title: "Connection Error",
          message: `Error submitting feedback: ${detail}`,
          variant: "danger"
        });
      } else {
        alert(`Error submitting feedback: ${detail}`);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleHide = () => {
    if (submitting) return;
    onClose();
  };

  const handleExited = () => {
    setFeedbackValue("");
    setFeedbackDetails("");
  };

  return (
    <BaseModal
      show={show}
      onHide={handleHide}
      onExited={handleExited}
      title="Provide Feedback"
      size="md"
      scrollableBody
      footer={
        <>
          <button type="button" className="rcc-ghost-btn" onClick={handleHide} disabled={submitting}>
            Cancel
          </button>
          <button
            type="button"
            className="rcc-primary-btn"
            onClick={handleSubmit}
            disabled={!feedbackValue || submitting}
          >
            {submitting ? "Submitting..." : "Submit Feedback"}
          </button>
        </>
      }
    >
      <>
        <div className="mb-3">
          <p className="mb-1">
            <strong>Question:</strong>
          </p>
          <p>{result.question}</p>
        </div>
        <Form>
          <Form.Group className="mb-3">
            <Form.Label className="small fw-semibold d-flex align-items-center">
              Was this answer helpful?
              <CustomTooltip 
                id="tooltip-feedback-info" 
                content="The feedback submitted in this form is saved in the reports/ folder at the root level of the AI SDK."
              >
                <i className="bi bi-info-circle info-icon ms-2"></i>
              </CustomTooltip>
            </Form.Label>
            <div>
              <Form.Check
                inline
                type="radio"
                id="positive-feedback"
                label="Yes"
                name="feedback"
                value="positive"
                checked={feedbackValue === "positive"}
                onChange={() => setFeedbackValue("positive")}
              />
              <Form.Check
                inline
                type="radio"
                id="negative-feedback"
                label="No"
                name="feedback"
                value="negative"
                checked={feedbackValue === "negative"}
                onChange={() => setFeedbackValue("negative")}
              />
            </div>
          </Form.Group>
          <Form.Group className="mb-3">
            <Form.Label className="small fw-semibold">Additional details (optional)</Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              value={feedbackDetails}
              onChange={(e) => setFeedbackDetails(e.target.value)}
              placeholder="Please provide any additional comments..."
            />
          </Form.Group>
        </Form>
      </>
    </BaseModal>
  );
};

export default FeedbackModal;
