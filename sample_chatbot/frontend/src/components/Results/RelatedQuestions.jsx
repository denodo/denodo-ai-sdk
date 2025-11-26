import React, { useState } from "react";
import Button from "react-bootstrap/Button";
import Badge from "react-bootstrap/Badge";

const RelatedQuestions = ({
  relatedQuestions,
  relatedQuestionsDeepQuery,
  onAskRelated,
  onAskDeepQuery,
}) => {
  const hasRegularQuestions =
    relatedQuestions && relatedQuestions.length > 0;
  const hasDeepQueryQuestions =
    relatedQuestionsDeepQuery && relatedQuestionsDeepQuery.length > 0;

  const [currentIndex, setCurrentIndex] = useState(0);
  const [animationClass, setAnimationClass] = useState("");

  if (!hasRegularQuestions && !hasDeepQueryQuestions) return null;

  const showCarouselArrows =
    hasRegularQuestions && relatedQuestions.length > 1;

  const navigate = (direction) => {
    if (!hasRegularQuestions || relatedQuestions.length <= 1) return;

    const total = relatedQuestions.length;
    let nextIndex;

    if (direction === "next") {
      nextIndex = (currentIndex + 1) % total;
      setAnimationClass("slide-in-right");
    } else {
      nextIndex = currentIndex === 0 ? total - 1 : currentIndex - 1;
      setAnimationClass("slide-in-left");
    }

    setCurrentIndex(nextIndex);

    setTimeout(() => {
      setAnimationClass("");
    }, 400);
  };

  const currentQuestion =
    hasRegularQuestions && relatedQuestions[currentIndex];

  return (
    <div className="d-flex flex-column align-items-start mt-3">
      {hasRegularQuestions && (
        <div className="w-100 mb-2">
          <Button
            variant="outline-light"
            size="sm"
            className="text-start w-100 related-question-btn"
            onClick={() => currentQuestion && onAskRelated(currentQuestion)}
          >
            <div className="d-flex align-items-center justify-content-between w-100">
              {showCarouselArrows && (
                <i
                  className="bi bi-chevron-left carousel-arrow-inner"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate("prev");
                  }}
                />
              )}
              <span
                className={`related-question-text flex-grow-1 text-center ${animationClass}`}
              >
                {currentQuestion}
              </span>
              {showCarouselArrows && (
                <i
                  className="bi bi-chevron-right carousel-arrow-inner"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate("next");
                  }}
                />
              )}
            </div>
          </Button>
        </div>
      )}

      {hasDeepQueryQuestions &&
        relatedQuestionsDeepQuery.map((q, index) => (
          <Button
            key={`deep_query-${index}`}
            variant="outline-warning"
            size="sm"
            className="mb-2 text-start w-100 analyst-question-btn"
            onClick={() => onAskDeepQuery(q)}
          >
            <div className="d-flex align-items-center justify-content-between w-100">
              <span
                className="text-white flex-grow-1"
                style={{ fontWeight: "500" }}
              >
                {q}
              </span>
              <Badge className="analyst-mode-badge">DeepQuery</Badge>
            </div>
          </Button>
        ))}
    </div>
  );
};

export default RelatedQuestions;


