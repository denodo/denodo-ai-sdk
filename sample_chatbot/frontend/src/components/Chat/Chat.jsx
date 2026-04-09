import React, { useEffect, useRef, useState } from "react";
import "./Chat.css";
import { useReport } from "../../contexts/ReportContext";
import ChatItem from "./ChatItem";
import NotificationToast from "../NotificationToast/NotificationToast";
import { actionTypes } from "../../reducers/chatReducer";

const Chat = ({
  results,
  dispatch,
  setCurrentQuestion,
  setQuestionType,
}) => {
  const resultsEndRef = useRef(null);
  const resultsContainerRef = useRef(null);
  const { generateReport } = useReport();
  const [reportGenerationStatus, setReportGenerationStatus] = useState({});

  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: "",
    variant: "light",
    title: "",
  });

  const scrollToBottom = () => {
    resultsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (results.length > 0) {
      scrollToBottom();
    }
  }, [results]);

  useEffect(() => {
    if (results.some(r => r.isExiting)) {
      const timer = setTimeout(() => {
        dispatch({ type: actionTypes.PURGE_EXITING_ITEMS });
      }, 400);
      return () => clearTimeout(timer);
    }
  }, [results, dispatch]);

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  const handleReportGeneration = async (result, colorPalette = "red") => {
    // Support for deep_query_metadata from toolCalls or top-level
    let metadata = result.deepquery_metadata;
    if (!metadata && result.toolCalls) {
        const dqCall = result.toolCalls.find(t => t.toolName === 'deep_query' && t.artifact && t.artifact.deepquery_metadata);
        if (dqCall) metadata = dqCall.artifact.deepquery_metadata;
    }

    if (!metadata) {
      console.error("No deepquery_metadata available for report generation");
      return;
    }

    if (reportGenerationStatus[result.uuid]) {
      console.log(
        "Report generation is already in progress for this result. Ignoring repeated request."
      );
      return;
    }

    setReportGenerationStatus((prevStatus) => ({
      ...prevStatus,
      [result.uuid]: true,
    }));

    setToastConfig({
      show: true,
      message: "Generating report... please wait.",
      variant: "info",
      title: "Processing",
    });

    try {
      await generateReport(metadata, result.question, colorPalette);

      setToastConfig({
        show: true,
        message: "Report generation finished successfully.",
        variant: "success",
        title: "Completed",
      });
    } catch (error) {
      console.error("Error generating report:", error);

      setToastConfig({
        show: true,
        message: "Error generating report.",
        variant: "danger",
        title: "Error",
      });
    } finally {
      setTimeout(() => {
        setReportGenerationStatus((prevStatus) => {
          const newStatus = { ...prevStatus };
          delete newStatus[result.uuid];
          return newStatus;
        });
      }, 3000);
    }
  };

  if (results.length === 0) {
    return null;
  }

  return (
    <div
      className="d-flex flex-column align-items-center w-100 text-light"
      ref={resultsContainerRef}
    >
      {results.map((result, index) => (
        <div
          key={result.uuid || `temp-${index}`}
          className={`w-100 ${result.isExiting ? 'chat-item-exit' : ''}`}
        >
          <ChatItem
            result={result}
            index={index}
            dispatch={dispatch}
            setCurrentQuestion={setCurrentQuestion}
            setQuestionType={setQuestionType}
            onGenerateReport={handleReportGeneration}
            isGeneratingReport={!!reportGenerationStatus[result.uuid]}
            resultsContainerRef={resultsContainerRef}
          />
        </div>
      ))}
      <div ref={resultsEndRef} />

      <NotificationToast
        show={toastConfig.show}
        message={toastConfig.message}
        variant={toastConfig.variant}
        title={toastConfig.title}
        onClose={handleToastClose}
      />
    </div>
  );
};

export default Chat;
