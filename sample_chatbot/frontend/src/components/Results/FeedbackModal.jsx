import React, { useState } from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";

const FeedbackModal = ({ show, onClose, result, setResults, feedbackEnabled }) => {
  const [feedbackValue, setFeedbackValue] = useState("");
  const [feedbackDetails, setFeedbackDetails] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!feedbackEnabled || !result) return null;

  const handleSubmit = async () => {
    if (!result.uuid) return;

    setSubmitting(true);

    try {
      const response = await fetch("submit_feedback", {
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

      const data = await response.json();

      if (response.ok) {
        setResults((prevResults) =>
          prevResults.map((item) =>
            item.uuid === result.uuid
              ? {
                  ...item,
                  feedback: feedbackValue,
                  feedbackDetails: feedbackDetails,
                }
              : item
          )
        );
        onClose();
      } else {
        alert(`Error submitting feedback: ${data.message}`);
      }
    } catch (error) {
      console.error("Error submitting feedback:", error);
      alert("An error occurred while submitting feedback.");
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
            <Form.Label>Was this answer helpful?</Form.Label>
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


