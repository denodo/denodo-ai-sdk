import React from "react";

const assetBaseUrl = import.meta.env.BASE_URL;

const WelcomeScreen = ({
  selectedChatbot,
  customLogoState,
  username,
  globalEnabled,
}) => {
  if (!selectedChatbot) {
    return (
      <div className="d-flex flex-column align-items-center w-100">
        {customLogoState === "absent" && (
          <>
            <h1 className="animate-fade-in-up delay-1 display-6 fw-normal text-dark mb-3 text-center">
              Hi {username ? username : "user"}, welcome to
            </h1>
            <div className="animate-fade-in-up delay-2">
              <h2
                className="text-shine px-3 py-2 display-4 m-0 text-center"
                style={{ fontWeight: 600, letterSpacing: "-1.5px" }}
              >
                Denodo Ask A Question
              </h2>
            </div>
          </>
        )}
        {globalEnabled ? (
          <p
            className="animate-fade-in-up delay-3 lead text-muted mt-4 mb-3 mx-auto text-center"
            style={{ maxWidth: "650px" }}
          >
            Select a specialized chatbot from the sidebar, or start typing below
            to use the general chat immediately.
          </p>
        ) : (
          <p
            className="animate-fade-in-up delay-3 lead text-muted mt-4 mb-3 mx-auto text-center"
            style={{ maxWidth: "550px" }}
          >
            To get started, please select one of the available chatbots from the
            sidebar.
          </p>
        )}
      </div>
    );
  }

  return (
    <div
      key={selectedChatbot.id}
      className="fade-in-smooth d-flex flex-column align-items-center text-center px-4"
    >
      {selectedChatbot.isGlobal ? (
        <img
          src={`${assetBaseUrl}denodo_chat_transparent.png`}
          alt="Chat"
          style={{
            width: "80px",
            height: "80px",
            objectFit: "contain",
            marginBottom: "20px",
          }}
          onError={(e) => {
            e.target.style.display = "none";
            e.target.nextSibling.style.display = "flex";
          }}
        />
      ) : selectedChatbot.icon ? (
        <img
          src={selectedChatbot.icon}
          alt={selectedChatbot.name}
          style={{
            width: "80px",
            height: "80px",
            objectFit: "contain",
            marginBottom: "20px",
          }}
          onError={(e) => {
            e.target.style.display = "none";
            e.target.nextSibling.style.display = "flex";
          }}
        />
      ) : null}
      <div
        className="align-items-center justify-content-center"
        style={{
          display:
            selectedChatbot.icon || selectedChatbot.isGlobal ? "none" : "flex",
          width: "80px",
          height: "80px",
          backgroundColor: "#f1f3f5",
          borderRadius: "50%",
          marginBottom: "20px",
        }}
      >
        <i
          className={`bi ${selectedChatbot.isGlobal ? "bi-chat-left-text" : "bi-robot"}`}
          style={{ fontSize: "2.5rem", color: "#143142" }}
        ></i>
      </div>
      {!selectedChatbot.isGlobal && (
        <h2 style={{ color: "#112533", fontWeight: 600, marginBottom: "15px" }}>
          {selectedChatbot.name}
        </h2>
      )}
      <p
        style={{
          color: "#6c757d",
          maxWidth: "600px",
          fontSize: "1.1rem",
          lineHeight: "1.6",
          marginTop: selectedChatbot.isGlobal ? "15px" : "0",
          marginBottom: 0,
          maxHeight: "100px",
          overflowY: "auto",
          paddingRight: "10px",
        }}
      >
        {selectedChatbot.description ||
          "I'm ready to help you. Ask me anything!"}
      </p>
    </div>
  );
};

export default WelcomeScreen;
