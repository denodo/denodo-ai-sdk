import React, { useState } from "react";
import Header from "./components/Header/Header";
import Results from "./components/Results";
import QuestionForm from "./components/QuestionForm";
import SignInModal from "./components/SignInModal";
import PDFManagementModal from "./components/PDFManagementModal";
import axios from 'axios';
import CSVUploadModal from "./components/CSVUploadModal";
import useSDK from './hooks/useSDK';

const App = () => {
  const [results, setResults] = useState([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [showSignInModal, setShowSignInModal] = useState(false);
  const [questionType, setQuestionType] = useState("general");
  const [showCSVModal, setShowCSVModal] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [completedRequestId, setCompletedRequestId] = useState(null);

  const handleRequestCompletion = (requestId) => {
    setCompletedRequestId(requestId);
  };

  const sdk = useSDK(setResults, handleRequestCompletion);

  const handleSignIn = async (userInformation) => {
    try {
      const response = await axios.post('login', userInformation);
      if (response.data.success) {
        setIsAuthenticated(true);
        setShowSignInModal(false);
      } else {
        alert('Invalid credentials. Please try again.');
      }
    } catch (error) {
      console.error('Sign-in error:', error);
      alert('An error occurred during sign-in. Please try again.');
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

  return (
    <div className="d-flex flex-column vh-100" style={{ backgroundColor: "#fff" }}>
      <Header 
        isAuthenticated={isAuthenticated} 
        setIsAuthenticated={setIsAuthenticated}
        handleClearResults={handleClearResults}
        showClearButton={results.length > 0}
        onLoadCSV={() => setShowCSVModal(true)}
      />
      <div className="flex-grow-1 overflow-auto" style={{ marginTop: "76px", marginBottom: "100px", padding: "0 20px" }}>
        {!isAuthenticated && (
          <div className="d-flex justify-content-center align-items-center h-100">
            <button 
              onClick={() => setShowSignInModal(true)} 
              className="btn btn-primary btn-lg"
              style={{ backgroundColor: '#112533', borderColor: '#112533', borderRadius: '1.25em' }}
            >
              Sign in
            </button>
          </div>
        )}
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
      <SignInModal
        show={showSignInModal}
        handleClose={() => setShowSignInModal(false)}
        onSignIn={handleSignIn}
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