import React, { useState, useEffect, useRef } from "react";
import "./Results.css";
import { useReport } from "../../contexts/ReportContext";
import ResultItem from "./ResultItem";
import NotificationToast from "../NotificationToast/NotificationToast";

const Results = ({
  results,
  setResults,
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
    resultsEndRef.current.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (results.length > 0) {
      scrollToBottom();
    }
  }, [results]);

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  const handleReportGeneration = async (result, colorPalette = "red") => {
    if (!result.deepquery_metadata) {
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
      await generateReport(result.deepquery_metadata, result.question, colorPalette);

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
        <ResultItem
          key={index}
          result={result}
          index={index}
          setResults={setResults}
          setCurrentQuestion={setCurrentQuestion}
          setQuestionType={setQuestionType}
          onGenerateReport={handleReportGeneration}
          isGeneratingReport={!!reportGenerationStatus[result.uuid]}
          resultsContainerRef={resultsContainerRef}
        />
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

export default Results;
