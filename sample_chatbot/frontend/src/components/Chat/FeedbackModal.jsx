import React, { useState } from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import { actionTypes } from "../../reducers/chatReducer";
import { buildApiUrl } from "../../api/client";
import CustomTooltip from "../CustomTooltip/CustomTooltip";

const FeedbackModal = ({ show, onClose, result, dispatch, resultIndex, feedbackEnabled }) => {
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
        onClose();
      } else {
        const detail =
          data.message ||
          `Feedback could not be saved (HTTP ${response.status}).`;
        alert(detail);
      }
    } catch (error) {
      console.error("Error submitting feedback:", error);
      const detail =
        error?.message ||
        "Unable to reach the server. Check your connection and try again.";
      alert(`Error submitting feedback: ${detail}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleHide = () => {
    if (submitting) return;
    setFeedbackValue("");
    setFeedbackDetails("");
    onClose();
  };

  return (
    <Modal show={show} onHide={handleHide} centered>
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>Provide Feedback</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <div className="mb-3">
          <p className="mb-1">
            <strong>Question:</strong>
          </p>
          <p>{result.question}</p>
        </div>
        <Form>
          <Form.Group className="mb-3">
            <Form.Label className="d-flex align-items-center">
              Was this answer helpful?
              <CustomTooltip 
                id="tooltip-feedback-info" 
                content="The feedback submitted in this form is saved in the reports/ folder at the root level of the AI SDK."
              >
                <i 
                  className="bi bi-info-circle ms-2" 
                  style={{ cursor: 'help', fontSize: '0.85rem', color: '#adb5bd', transition: 'color 0.2s' }}
                  onMouseEnter={(e) => e.target.style.color = '#112533'}
                  onMouseLeave={(e) => e.target.style.color = '#adb5bd'}
                ></i>
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
            <Form.Label>Additional details (optional)</Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              value={feedbackDetails}
              onChange={(e) => setFeedbackDetails(e.target.value)}
              placeholder="Please provide any additional comments..."
            />
          </Form.Group>
        </Form>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="light" onClick={handleHide} disabled={submitting}>
          Cancel
        </Button>
        <Button
          variant="dark"
          onClick={handleSubmit}
          disabled={!feedbackValue || submitting}
        >
          {submitting ? "Submitting..." : "Submit Feedback"}
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default FeedbackModal;