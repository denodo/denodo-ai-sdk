import React, { useState } from "react";
import Header from "./components/Header/Header";
import Results from "./components/Results/Results";
import QuestionForm from "./components/QuestionForm";
import PDFManagementModal from "./components/PDFManagementModal";
import axios from 'axios';
import CSVUploadModal from "./components/CSVUploadModal";
import useSDK from './hooks/useSDK';
import LoginPage from "./components/LoginPage/LoginPage";

const App = () => {
  const [results, setResults] = useState([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [questionType, setQuestionType] = useState("general");
  const [showCSVModal, setShowCSVModal] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [completedRequestId, setCompletedRequestId] = useState(null);
  const [customLogoFailed, setCustomLogoFailed] = useState(false);

  const handleRequestCompletion = (requestId) => {
    setCompletedRequestId(requestId);
  };

  const sdk = useSDK(setResults, handleRequestCompletion);

  const handleLogoError = () => {
    setCustomLogoFailed(true);
  };

  const renderLogo = () => {
    const denodoLogo = (
      <img
        alt="Denodo company logo"
        src={`${process.env.PUBLIC_URL}/denodo.png`}
        height="30"
        className="d-inline-block align-top"
      />
    );

    if (!customLogoFailed) {
      return (
        <React.Fragment>
          {denodoLogo}
          {" + "}
          <img
            alt="Custom company logo"
            src={`${process.env.PUBLIC_URL}/logo.png`}
            height="30"
            className="d-inline-block align-top"
            onError={handleLogoError}
          />
        </React.Fragment>
      );
    } else {
      return denodoLogo;
    }
  };

  const handleSignIn = async (userInformation) => {
    try {
      const response = await axios.post('login', userInformation);
      if (response.data.success) {
        setIsAuthenticated(true);
      } else {
        const errorMessage = response.data.message || 'Invalid credentials. Please try again.';
        alert(errorMessage);
      }
    } catch (error) {
      const errorMessage = error.response?.data?.message || 'An error occurred during sign-in. Please try again.';
      alert(errorMessage);
    }
  };

  const handleClearResults = async () => {
    try {
      setResults([]);
      await axios.post(`clear_history`);
    } catch (error) {
      console.error("There was an error clearing the memory!", error);
    }
  };

  const handleCSVUpload = async (file, description, delimiter = ';') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('description', description);
    formData.append('delimiter', delimiter);

    try {
      const response = await axios.post('update_csv', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.status === 200) {
        setShowCSVModal(false);
        handleClearResults();
        alert('CSV file uploaded successfully!');
      }
    } catch (error) {
      console.error('Error uploading CSV:', error);
      alert(error.response?.data?.message || 'An error occurred while uploading the CSV file.');
    }
  };

  if (!isAuthenticated) {
    return <LoginPage onSignIn={handleSignIn} renderLogo={renderLogo} />;
  }

  return (
    <div className="d-flex flex-column vh-100" style={{ backgroundColor: "#fff" }}>
      <Header
        isAuthenticated={isAuthenticated}
        setIsAuthenticated={setIsAuthenticated}
        handleClearResults={handleClearResults}
        showClearButton={results.length > 0}
        onLoadCSV={() => setShowCSVModal(true)}
        renderLogo={renderLogo}
      />
      <div className="flex-grow-1 overflow-auto" style={{ marginTop: "76px", marginBottom: "100px", padding: "0 20px" }}>
        <Results
          results={results}
          setResults={setResults}
          setCurrentQuestion={setCurrentQuestion}
          setQuestionType={setQuestionType}
        />
      </div>
      <QuestionForm
        results={results}
        setResults={setResults}
        isAuthenticated={isAuthenticated}
        questionType={questionType}
        setQuestionType={setQuestionType}
        currentQuestion={currentQuestion}
        setCurrentQuestion={setCurrentQuestion}
        sdk={sdk}
        completedRequestId={completedRequestId}
      />
      <CSVUploadModal
        show={showCSVModal}
        handleClose={() => setShowCSVModal(false)}
        onUpload={handleCSVUpload}
      />
      <PDFManagementModal />
    </div>
  );
};

export default App;
